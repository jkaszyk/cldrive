# Copyright (C) 2017 Chris Cummins.
#
# This file is part of cldrive.
#
# Cldrive is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Cldrive is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cldrive.  If not, see <http://www.gnu.org/licenses/>.
#
import sys

import numpy as np
import pyopencl as cl

from cldrive import *

NDRange = namedtuple('NDRange', ['x', 'y', 'z'])

class Driver(object):
    def __init__(self, env: OpenCLEnvironment, src: str,
                 optimizations: bool=True, debug: bool=False):
        """
        OpenCL kernel.

        Arguments:
            env (OpenCLEnvironment): The OpenCL environment to run the
                kernel in.
            src (str): The OpenCL kernel source.
            optimizations(bool, optional): Whether to enable or disbale OpenCL
                compiler optimizations.
            debug(bool, optional): If true, silence the OpenCL compiler.

        Raises:
            ValueError: if input types are incorrect
        """
        self.debug = debug

        # set input attributes
        assert_or_raise(len(env) == 2, ValueError,
                         "env tuple is of incorrect length")
        assert_or_raise(isinstance(env[0], cl.Context), ValueError,
                         "env[0] is not a pyopencl.Context instance")
        assert_or_raise(isinstance(env[1], cl.CommandQueue), ValueError,
                         "env[1] is not a pyopencl.CommandQueue instance")
        self.env = OpenCLEnvironment(ctx=env[0], queue=env[1])

        assert_or_raise(isinstance(src, str), ValueError,
                         "input source is not a string")
        self.src = src
        self.optimizations = optimizations

        # OpenCL compiler flags
        if self.optimizations:
            self.build_flags = []
            self._log("OpenCL optimizations: on")
        else:
            self.build_flags = ['-cl-opt-disable']
            self._log("OpenCL optimizations: off")

        # parse args first as this is most likely to raise an error
        self.args = extract_args(self.src)

        if self.debug:
            os.environ['PYOPENCL_COMPILER_OUTPUT'] = '1'
        else:
            os.environ['PYOPENCL_COMPILER_OUTPUT'] = '0'

        self.program = cl.Program(self.env.ctx, self.src).build(
            self.build_flags)
        kernels = self.program.all_kernels()
        # extract_args() should already have raised an error if there's more
        # than one kernel:
        assert(len(kernels) == 1)
        self.kernel = kernels[0]

    def _log(self, *args, **kwargs):
        if self.debug:
            print(*args, **kwargs, file=sys.stderr)

    def __call__(self, inputs: np.array, gsize: NDRange, lsize: NDRange,
                 timeout: float=-1) -> np.array:
        """
        Run kernel with input payload

        Arguments:
            timeout (float, optional): Cancel execution if it has not completed
                after this many seconds. A value <= 0 means never time out.

        Returns:
            np.array: A numpy array of the same shape as the inputs, with the
                values after running the OpenCL kernel.

        Raises:
            TypeError: If an input is of an incorrect type.
            LogicError: If the input types do not match OpenCL kernel types.

        TODO:
            * Implement timeout.
        """
        # copy inputs into the expected data types
        data = np.array([np.array(d).astype(a.numpy_type)
                         for d, a in zip(inputs, self.args)])

        # sanity check that there are enough the correct number of inputs
        data_indices = [i for i, arg in enumerate(self.args) if not arg.is_local]
        assert_or_raise(len(data_indices) == len(data), ValueError,
                        "Incorrect number of inputs provided")

        assert_or_raise(len(gsize) == 3, TypeError)
        assert_or_raise(len(lsize) == 3, TypeError)
        gsize, lsize = NDRange(*gsize), NDRange(*lsize)

        # scalar_gsize is the product of the global NDRange.
        scalar_gsize, scalar_lsize = 1, 1
        for g, l in zip(gsize, lsize):
            scalar_gsize *= g
            scalar_lsize *= l

        self._log(f"""\
3-D global size {scalar_gsize} = [{gsize.x}, {gsize.y}, {gsize.z}]
3-D local size {scalar_lsize} = [{lsize.x}, {lsize.y}, {lsize.z}]""")

        # buffer size is the scalar global size, or the size of the largest
        # input, which is bigger
        buf_size = max(scalar_gsize, *[x.size for x in data])

        # assemble argtuples
        ArgTuple = namedtuple('ArgTuple', ['hostdata', 'devdata'])
        argtuples = []
        data_i = 0
        for i, arg in enumerate(self.args):
            if arg.is_global:
                data[data_i] = data[data_i].astype(arg.numpy_type)
                hostdata = data[data_i]
                # determine flags to pass to OpenCL buffer creation:
                flags = cl.mem_flags.COPY_HOST_PTR
                if arg.is_const:
                    flags |= cl.mem_flags.READ_ONLY
                else:
                    flags |= cl.mem_flags.READ_WRITE
                buf = cl.Buffer(self.env.ctx, flags, hostbuf=hostdata)

                devdata, data_i = buf, data_i + 1
            elif arg.is_local:
                nbytes = buf_size * arg.vector_width * arg.numpy_type.itemsize
                buf = cl.LocalMemory(nbytes)

                hostdata, devdata = None, buf
            elif not arg.is_pointer:
                hostdata = None
                devdata, data_i = arg.numpy_type(data[data_i]), data_i + 1
            else:
                # argument is neither global or local, but is a pointer?
                raise ValueError(f"unknown argument type '{arg}'")
            argtuples.append(ArgTuple(hostdata=hostdata, devdata=devdata))

        assert_or_raise(len(data) == data_i, ValueError,
                        "failed to set input arguments")

        # clear any existing tasks in the command queue:
        self.env.queue.flush()

        # copy host -> device
        for argtuple in argtuples:
            if argtuple.hostdata is not None:
                cl.enqueue_copy(
                    self.env.queue, argtuple.devdata, argtuple.hostdata,
                    is_blocking=False)

        kernel_args = [argtuple.devdata for argtuple in argtuples]

        try:
            self.kernel.set_args(*kernel_args)
        except cl.LogicError as e:
            raise TypeError(e)

        # run the kernel
        self.kernel(self.env.queue, gsize, lsize, *kernel_args)

        # copy device -> host
        for arg, argtuple in zip(self.args, argtuples):
            if argtuple.hostdata is not None and not arg.is_const:
                cl.enqueue_copy(
                    self.env.queue, argtuple.hostdata, argtuple.devdata,
                    is_blocking=False)

        # wait for queue to finish
        self.env.queue.flush()

        return data


    def __repr__(self) -> str:
        return self.src
