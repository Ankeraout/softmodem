#ifndef __INCLUDE_PLATFORM_SOCKET_HPP__
#define __INCLUDE_PLATFORM_SOCKET_HPP__

#ifdef PLATFORM_UNIX
#include <unistd.h>
#endif

namespace softmodem {
namespace util {

class Socket {
    public:
    Socket();
};

}
}

#endif
