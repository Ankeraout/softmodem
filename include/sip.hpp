#ifndef __INCLUDE_SIP_H__
#define __INCLUDE_SIP_H__

#include <cstdint>
#include <random>
#include <string>

namespace softmodem {
namespace sip {

enum class ClientState {
    STOPPED,
    STARTING,
    REGISTERING,
    REGISTERED,
    STOPPING
};

enum class CallState {
    DIALING,
    RINGING,
    CONNECTED,
    TERMINATED
};

class SIPCall {

};

class SIPClient {
public:
    SIPClient(
        std::string const& p_username,
        std::string const& p_password,
        std::string const& p_domain,
        std::uint16_t p_serverPort,
        std::uint16_t p_localPort
    );
    ClientState getState(void) const;
    void start(void);
    void stop(void);
    SIPCall *dial(std::string const& p_number);

private:
    std::string m_username;
    std::string m_password;
    std::string m_domain;
    std::uint16_t m_serverPort;
    std::uint16_t m_localPort;
    std::string m_localIP;
};

}
}

#endif
