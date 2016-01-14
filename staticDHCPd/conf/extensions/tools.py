#!/usr/bin/env python
"""
Additional tools for processing DHCP requests

Copyright 2016 NaviSite Inc. - A Time Warner Cable Company
"""
import pickle
from libpydhcpserver.dhcp_types.ipv4 import IPv4
from staticdhcpdlib.databases.generic import Definition

def filterRetrievedDefinitions(definitions, packet, packet_type, mac,
                               ip, giaddr, pxe_options):
    """
    Filter the possible definitions by using the extra information

    :param list: A list of definitions types to filter
    :param basestring packet_type: The type of packet being processed.
    :param str mac: The MAC of the responding interface, in network-byte
        order.
    :param :class:`libpydhcpserver.dhcp_types.ipv4.IPv4` ip: Value of
        DHCP packet's `requested_ip_address` field.
    :param :class:`libpydhcpserver.dhcp_types.ipv4.IPv4` giaddr: Value of
        the packet's relay IP address
    :param namedtuple pxe_options: PXE options
    :return :class:`databases.generic.Definition` definition: The associated
        definition; None if no "lease" is available.
    """
    if not definitions:
        return None
    elif len(definitions) == 1:
        #replicates current functionality, may want to change
        return definitions[0]

    for definition in definitions:
        #TODO: Handle RENEW/REBIND where we know the IP address
        if giaddr and definition.subnet_mask:
            #We can determine the correct definition since the
            # giaddr should exist in the same network as
            # the response IP address
            #TODO: What happens under multiple relays in the chain?
            if giaddr.isSubnetMember(definition.ip, definition.subnet_mask):
               return definition
    else:
        return None


class Memcacher(object):
    def __init__(self, addresses, expire_time):
        """
        Class to facilitate storing and fetching
          Definitions in memcache
        """
        import memcache
        self.mc_client = memcache.Client(addresses)
        self.expire_time = expire_time

    def lookupMAC(self, mac):
        data = self.mc_client.get(str(mac))
        if data:
            results = []
            for datum in pickle.loads(data):
                (ip, hostname, extra, subnet_id) = datum
                subnet_str = self._create_subnet_key(subnet_id)
                details = self.mc_client.get(subnet_str)
                if details:
                    results.append(Definition(
                     ip=ip, lease_time=details[6], subnet=subnet_id[0],
                     serial=subnet_id[1], hostname=hostname,
                     gateways=details[0], subnet_mask=details[1],
                     broadcast_address=details[2], domain_name=details[3],
                     domain_name_servers=details[4], ntp_servers=details[5],
                     extra=extra
                    ))
            if results:
                return results
        return None

    def cacheMAC(self, mac, definitions):
        if not isinstance(definitions, (list,tuple)):
            definitions = [definitions]

        mac_list = []
        for definition in definitions:
            subnet_id = (definition.subnet, definition.serial)
            subnet_str = self._create_subnet_key(subnet_id)
            mac_list.append((definition.ip, definition.hostname,
                             definition.extra, subnet_id))
            self.mc_client.set(
             subnet_str,
             (definition.gateways, definition.subnet_mask,
              definition.broadcast_address, definition.domain_name,
              definition.domain_name_servers, definition.ntp_servers,
              definition.lease_time
             ),
             self.expire_time
            )

        self.mc_client.set(
         str(mac), pickle.dumps(mac_list), self.expire_time
        )

    def _create_subnet_key(self, subnet_id):
        return "%s-%i" % (subnet_id[0].replace(" ", "_"), subnet_id[1])
