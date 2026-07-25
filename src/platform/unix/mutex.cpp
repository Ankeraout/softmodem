#ifdef PLATFORM_UNIX

#include <stdexcept>
#include <pthread.h>
#include "platform/mutex.hpp"

softmodem::util::Mutex::Mutex(void) {
    pthread_mutexattr_t l_attr;
    
    if(pthread_mutexattr_init(&l_attr) != 0) {
        throw std::runtime_error("Failed to initialize mutex attr object.");
    }

    if(pthread_mutexattr_settype(&l_attr, PTHREAD_MUTEX_RECURSIVE) != 0) {
        pthread_mutexattr_destroy(&l_attr);
        throw std::runtime_error("Failed to set mutex type.");
    }

    if(pthread_mutex_init(&m_mutex, &l_attr) != 0) {
        pthread_mutexattr_destroy(&l_attr);
        throw std::runtime_error("Failed to initialize mutex.");
    }

    pthread_mutexattr_destroy(&l_attr);
}

softmodem::util::Mutex::~Mutex() {
    pthread_mutex_destroy(&m_mutex);
}

void softmodem::util::Mutex::acquire(void) {
    if(pthread_mutex_lock(&m_mutex) != 0) {
        throw std::runtime_error("Failed to lock mutex.");
    }
}

void softmodem::util::Mutex::release(void) {
    if(pthread_mutex_unlock(&m_mutex) != 0) {
        throw std::runtime_error("Failed to unlock mutex.");
    }
}

#endif
