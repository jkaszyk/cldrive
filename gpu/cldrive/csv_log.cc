// Copyright (c) 2016, 2017, 2018, 2019 Chris Cummins.
// This file is part of cldrive.
//
// cldrive is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// cldrive is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with cldrive.  If not, see <https://www.gnu.org/licenses/>.

#include <iostream>
#include <string>

#include "gpu/cldrive/csv_log.h"
#include "phd/logging.h"

namespace gpu {
namespace cldrive {

// Print a value only if it is not zero.
template <typename T>
std::ostream& NullIfZero(std::ostream& stream, const T& value) {
  if (value != 0) {
    stream << value;
  }
  return stream;
}

// Print a value only if it is not empty().
template <typename T>
std::ostream& NullIfEmpty(std::ostream& stream, const T& value) {
  if (!value.empty()) {
    stream << value;
  }
  return stream;
}

// Print a value only if it is not less than zero.
template <typename T>
std::ostream& NullIfNegative(std::ostream& stream, const T& value) {
  if (value >= 0) {
    stream << value;
  }
  return stream;
}

std::ostream& operator<<(std::ostream& stream, const CsvLogHeader& header) {
  stream << "instance,device,build_opts,kernel,work_item_local_mem_size,"
         << "work_item_private_mem_size,global_size_x,global_size_y,global_size_z,local_size_x,local_size_y,local_size_z,outcome,"
         << "transferred_bytes,runtime_ns\n";
  return stream;
}

std::ostream& operator<<(std::ostream& stream, const CsvLog& log) {
  stream << log.kernel_file_name_ << "," << log.instance_id_ << "," << log.device_ << "," << log.build_opts_
         << ",";
  NullIfEmpty(stream, log.kernel_) << ",";
  NullIfNegative(stream, log.work_item_local_mem_size_) << ",";
  NullIfNegative(stream, log.work_item_private_mem_size_) << ",";
  NullIfZero(stream, log.global_size_) << ",";
  NullIfZero(stream, log.global_size_y_) << ",";
  NullIfZero(stream, log.global_size_z_) << ",";
  NullIfZero(stream, log.local_size_) << ",";
  NullIfZero(stream, log.local_size_y_) << ",";
  NullIfZero(stream, log.local_size_z_) << ",";
  stream << log.outcome_ << ",";
  NullIfZero(stream, log.transferred_bytes_) << ",";
  NullIfZero(stream, log.runtime_ms_) << std::endl;
  return stream;
}

/*static*/ CsvLog CsvLog::FromProtos(
    std::string kernel_file_name,
    int instance_id, const CldriveInstance* const instance,
    const CldriveKernelInstance* const kernel_instance,
    const CldriveKernelRun* const run,
    const gpu::libcecl::OpenClKernelInvocation* const log) {
  CsvLog csv;

  csv.kernel_file_name_ = kernel_file_name;
  csv.instance_id_ = instance_id;

  CHECK(instance) << "CldriveInstance pointer cannot be null";
  csv.device_ = instance->device().name();
  csv.build_opts_ = instance->build_opts();
  csv.work_item_local_mem_size_ = -1;
  csv.work_item_private_mem_size_ = -1;

  csv.outcome_ = CldriveInstance::InstanceOutcome_Name(instance->outcome());
  if (kernel_instance) {
    csv.kernel_ = kernel_instance->name();
    csv.work_item_local_mem_size_ =
        kernel_instance->work_item_local_mem_size_in_bytes();
    csv.work_item_private_mem_size_ =
        kernel_instance->work_item_private_mem_size_in_bytes();

    csv.outcome_ = CldriveKernelInstance::KernelInstanceOutcome_Name(
        kernel_instance->outcome());
    if (run) {
      csv.outcome_ = CldriveKernelRun::KernelRunOutcome_Name(run->outcome());
      if (log) {
        csv.outcome_ = "PASS";
        csv.global_size_ = log->global_size();
	csv.global_size_y_ = log->global_size_y();
	csv.global_size_z_ = log->global_size_z();
        csv.local_size_ = log->local_size();
	csv.local_size_y_ = log->local_size_y();
	csv.local_size_z_ = log->local_size_z();
        csv.runtime_ms_ = log->runtime_ms();
        csv.transferred_bytes_ = log->transferred_bytes();
      }
    }
  }

  return csv;
}

}  // namespace cldrive
}  // namespace gpu
