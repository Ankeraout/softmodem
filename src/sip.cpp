#include "sip.hpp"

softmodem::sip::SIPClient::SIPClient(
    std::string const& p_username,
    std::string const& p_password,
    std::string const& p_domain,
    std::uint16_t p_serverPort,
    std::uint16_t p_localPort
) :
m_username(p_username),
m_password(p_password),
m_domain(p_domain),
m_serverPort(p_serverPort),
m_localPort(p_localPort) {
    
}

