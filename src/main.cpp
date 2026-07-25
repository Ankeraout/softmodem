#include <cstdio>
#include "sip.hpp"

int main(void) {
    std::printf("Hello, world!\n");
    softmodem::sip::SIPClient l_client(
        "user",
        "pass",
        "192.168.0.5",
        5060,
        5060
    );

    
    return 0;
}
