# -*- encoding: utf-8 -*-
"""
Provides a basic HTTP(S)-based database for sites that work using RESTful models.

Specifically, this module implements a very generic REST-JSON system, with
optional support for caching. To implement another protocol, only one method
needs to be rewritten, so just look for the comments.

To use this module, make the following changes to conf.py:
    Locate the DATABASE_ENGINE line and replace it with the following two lines:
        import httpdb
        DATABASE_ENGINE = httpdb.HTTPDatabase #or httpdb.HTTPCachingDatabase

    Anywhere above the 'import httpdb' line, define any of the following
    parameters that you need to override:
        #The address of your webservice; MUST BE SET
        X_HTTPDB_URI = 'http://example.org/lookup'
        #Whether 'mac' should be an element in a POSTed JSON object, like
        #{"mac": "aa:bb:cc:dd:ee:ff"}, or encoded in the query-string as 'mac',
        #like "mac=aa%3Abb%3Acc%3Add%3Aee%3Aff"; DEFAULTS TO True
        X_HTTPDB_POST = True
        #Any custom HTTP headers your service requires; DEFAULTS TO {}
        X_HTTPDB_HEADERS = {
            'Your-Company-Token': "hello",
        }
        #If using HTTPCachingDatabase, the maximum number of requests to run
        #at a time; successive requests will block; DEFAULTS TO (effectively)
        #INFINITE
        X_HTTPDB_CONCURRENCY_LIMIT = 10

For a list of all parameters you may define, see below.

If concurrent connections to your HTTP server should be limited, use
HTTPCachingDatabase instead of HTTPDatabase.

Like staticDHCPd, this module under the GNU General Public License v3
(C) Neil Tallim, 2014 <flan@uguu.ca>

Created in response to a request from Aleksandr Chusov.
"""
################################################################################
#Rewrite _parse_server_response() as needed to work with your service.
################################################################################
def _parse_server_response(json_data):
    """
    Transforms a server-response that looks like this...
    {
        "ip": "192.168.0.1",
        "hostname": "any-valid-hostname", //may be omitted or null
        "gateway": "192.168.0.1", //may be omitted or null
        "subnet_mask": "255.255.255.0", //may be omitted or null
        "broadcast_address": "192.168.0.255", //may be omitted or null
        "domain_name": "example.org", //may be omitted or null
        "domain_name_servers": ["192.168.0.1", "192.168.0.2", "192.168.0.3"], //may be omitted or null
        "ntp_servers": ["192.168.0.1", "192.168.0.2", "192.168.0.3"], //may be omitted or null
        "lease_time": 3600,
        "subnet": "subnet-id",
        "serial": 0,
        "extra": {...}, //any extra attributes you would like in the lease-definition; may be omitted or null
    }
    ...into a Definition-object.
    """
    result = Definition(
        ip=json_data['ip'], lease_time=json_data['lease_time'],
        subnet=json_data['cidr'], serial=json_data['serial'],
        hostname=json_data.get('hostname'),
        gateways=json_data.get('gateway'),
        subnet_mask=json_data.get('netmask'),
        broadcast_address=json_data.get('broadcast_address'),
        domain_name=json_data.get('domain_name'),
        domain_name_servers=json_data.get('domain_name_servers'),
        ntp_servers=json_data.get('ntp_servers'),
        extra=json_data.get('extra'),
    )

    if not result['domain_name_servers'] and hasattr(config, 'DEFAULT_NAME_SERVERS', None):
        result['domain_name_servers'] = config.X_HTTPDB_DEFAULT_NAME_SERVERS

    if not result['lease_time'] and hasattr(config, 'DEFAULT_LEASE_TIME', None):
        result['lease_time'] = config.X_HTTPDB_DEFAULT_LEASE_TIME

    return result

#Do not touch anything below this line
################################################################################
import json
import logging
import urllib2

from staticdhcpdlib.databases.generic import (Definition, Database, CachingDatabase)

_logger = logging.getLogger("extension.httpdb")

#This class implements your lookup method; to customise this module for your
#site, all you should need to do is edit this section.
class _HTTPLogic(object):
    def __init__(self):
        from staticdhcpdlib import config

        try:
            self._uri = config.X_HTTPDB_URI
        except AttributeError:
            raise AttributeError("X_HTTPDB_URI must be specified in conf.py")
        self._headers = getattr(config, 'X_HTTPDB_HEADERS', {})
        additional_info = getattr(config, 'X_HTTPDB_ADDITIONAL_INFO', {})
        string_list = ['&%s=%s' % (key, value) for key, value in additional_info.iteritems()]
        self._additional_info = ''.join(string_list)
        #self._post = getattr(config, 'X_HTTPDB_POST', True)

    def _lookupMAC(self, mac):
        """
        Performs the actual lookup operation; this is the first thing you should
        study when customising for your site.
        """
        global _parse_server_response
        #If you need to generate per-request headers, add them here
        headers = self._headers.copy()

        #You can usually ignore this if-block, though you could strip out whichever method you don't use
        url = "%(uri)s?mac=%(mac)s%(add_info)s" % {
         'uri': self._uri,
         'mac': str(mac).replace(':', '%3A'),
         'add_info': self._additional_info
        }

        request = urllib2.Request(
         url,
         headers=headers,
        )

        _logger.debug("Sending request to '%(uri)s' for '%(mac)s'... %(url)s" % {
         'uri': self._uri,
         'mac': str(mac),
         'url': url
        })
        try:
            response = urllib2.urlopen(request)
            _logger.debug("MAC response received from '%(uri)s' for '%(mac)s'" % {
             'uri': self._uri,
             'mac': str(mac),
            })
            results = json.loads(response.read())

            if not results: #The server sent back 'null' or an empty object
                _logger.debug("Unknown MAC response from '%(uri)s' for '%(mac)s'" % {
                 'uri': self._uri,
                 'mac': str(mac),
                })
                return None

            definitions = [_parse_server_response(result) for result in results]

            _logger.debug("Known MAC response from '%(uri)s' for '%(mac)s'" % {
             'uri': self._uri,
             'mac': str(mac),
            })
            return definitions
        except Exception, e:
            _logger.error("Failed to lookup '%(mac)s' on '%(uri)s': %(error)s" % {
             'uri': self._uri,
             'mac': str(mac),
             'error': str(e),
            })
            raise

    def _retrieveDefinition(self, packet_or_mac, packet_type=None, mac=None, ip=None,
                            giaddr=None, pxe=None, pxe_options=None):
        # TODO - update this function to return None if additional info is not avail
        #        to check against subnet - also add verification of subnet
        if all(x is None for x in [packet_type, mac, ip, giaddr, pxe, pxe_options]):
            #packet_or_mac is mac
            result = self._lookupMAC(packet_or_mac)
            if result and isinstance(result, (list,tuple)) and len(result) == 1:
                return result[0]
            else:
                return None
        else:
            return None


class HTTPDatabase(Database, _HTTPLogic):
    def __init__(self):
        _HTTPLogic.__init__(self)

    def lookupMAC(self, packet_or_mac, packet_type=None, mac=None, ip=None,
                  giaddr=None, pxe=None, pxe_options=None):
        return self._retrieveDefinition(packet_or_mac, packet_type, mac, ip,
                                        giaddr, pxe_options)

class HTTPCachingDatabase(CachingDatabase, _HTTPLogic):
    def __init__(self):
        if hasattr(config, 'X_HTTPDB_CONCURRENCY_LIMIT'):
            CachingDatabase.__init__(self, concurrency_limit=config.X_HTTPDB_CONCURRENCY_LIMIT)
        else:
            CachingDatabase.__init__(self)
        _HTTPLogic.__init__(self)

# def _handle_unknown_mac(packet, packet_type, mac, ip,
#                            giaddr, pxe_options):
#     HTTPDatabase().lookupMAC(packet, packet_type, mac, ip,
#                                       giaddr, pxe_options)
