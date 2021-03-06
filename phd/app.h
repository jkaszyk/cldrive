#pragma once

#include "gflags/gflags.h"

namespace phd {

// Initialize an application. This should be called first in main(). This takes
// care of handling flags and setting the app's usage string.
void InitApp(int* argc, char*** argv, const char* usage_string = "");

}  // namespace phd