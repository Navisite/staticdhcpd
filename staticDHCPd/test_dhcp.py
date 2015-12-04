from libpydhcpserver import dhcp
from libpydhcpserver.dhcp_types import packet
from libpydhcpserver.dhcp_types import mac
import socket
import random

HARDWARE_MAC = '0a:00:27:00:00:00'
HARDWARE_IP = '192.168.56.1'
CLIENT_PORT = 68
RANDR = random.Random()

_ETH_P_SNAP = 0x0005
#send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def genxid():
    decxid = RANDR.randint(0,0xffffffff)
    xid = []
    for i in xrange(4):
        xid.insert(0, decxid & 0xff)
        decxid = decxid >> 8
    return xid

class Sender(dhcp._L2Responder):
    def __init__(self):
        #self.send_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(_ETH_P_SNAP))
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.send_socket.bind((HARDWARE_IP, CLIENT_PORT))
        self.send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        dhcp._L2Responder.__init__(self, '0.0.0.0', HARDWARE_MAC, qtags=None)

    def send(self, packet):
        return self.send_socket.sendto(packet.encodePacket(), ('<broadcast>', 67))
SENDER = Sender()

def test_discover(chaddr, giaddr):
    discover_packet = packet.DHCPPacket()
    discover_packet.setOption(53, 1) #Make to discover packet

    discover_packet.setOption(55, [1, 2, 3, 6, 12, 15, 26, 28, 42, 44, 47, 119, 121])
    # Option 55 = Parameter Request List
    #  Options based off an Ubuntu VM's actual request
    #    1: Subnet Mask
    #    2: Time Offset
    #    3: Router
    #    6: Domain Server
    #    12: Hostname
    #    15: Domain Name
    #    26: MTU Interface
    #    28: Broadcast Address
    #    42: NTP Servers
    #    44: NETBIOS Name Srv
    #    47: NETBIOS Scope
    #    119: Domain Search
    #    121: Classless Static Route Option
    discover_packet.setHardwareAddress(mac.MAC(chaddr)._mac)
    discover_packet.setOption('op', 1)
    discover_packet.setOption('htype', 1)
    discover_packet.setOption('hlen', 6)
    discover_packet.setOption('hops', 0)
    xid = genxid()
    discover_packet.setOption('xid', xid)
    discover_packet.setOption('giaddr', giaddr)
    # discover_packet._selected_options = set([1, 2, 3, 6, 12, 15, 26, 28, 42, 44,
    #                                          47, 51, 53, 54, 58, 59, 119, 121])
    # #Additional options not specifically requested; forced answer
    # # 51: Address Time
    # # 53: DHCP Message Type
    # # 54: DHCP Server ID
    # # 58: Renewal Time
    # # 59: Rebinding Time
    SENDER.send(discover_packet)

test_mac = '00:50:56:92:78:46'
test_giaddr = '10.193.10.90'

def genmac():
    i = []
    for z in xrange(6):
        i.append(RANDR.randint(0,255))
    return ':'.join(map(lambda x: "%02x"%x,i))

def load_test():
    for i in range(1000):
        test_discover(genmac(), test_giaddr)
