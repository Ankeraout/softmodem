#ifndef __INCLUDE_PLATFORM_MUTEX_HPP__
#define __INCLUDE_PLATFORM_MUTEX_HPP__

#ifdef PLATFORM_UNIX
#include <pthread.h>
#endif

namespace softmodem {
namespace util {

class Mutex {
    public:
    Mutex();
    ~Mutex();
    void release();
    void acquire();

    private:
#ifdef PLATFORM_UNIX
    pthread_mutex_t m_mutex;
#endif
};

}
}

#endif
