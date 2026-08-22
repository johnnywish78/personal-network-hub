import 'package:flutter_test/flutter_test.dart';
import 'package:rdnbenet/core/services/xray_process_manager.dart';

void main() {
  late XrayProcessManager manager;

  setUp(() {
    manager = XrayProcessManager();
  });

  group('extractOutboundAddress', () {
    test('reads flattened Xray outbound settings.address', () {
      final config = {
        'inbounds': [
          {'protocol': 'socks', 'port': 10808},
        ],
        'outbounds': [
          {
            'tag': 'proxy',
            'protocol': 'vless',
            'settings': {
              'address': 'pp.parsaoo.ir',
              'port': 443,
              'id': '1da0fcb1-28f8-44f4-ae97-7387b90ebda2',
              'encryption': 'none',
            },
          },
          {'protocol': 'freedom', 'tag': 'direct'},
        ],
      };

      expect(manager.extractOutboundAddress(config), 'pp.parsaoo.ir');
    });

    test('reads classic vnext address', () {
      final config = {
        'outbounds': [
          {
            'protocol': 'vless',
            'settings': {
              'vnext': [
                {
                  'address': 'old.example.com',
                  'port': 443,
                  'users': [
                    {'id': 'uuid', 'encryption': 'none'},
                  ],
                },
              ],
            },
          },
        ],
      };

      expect(manager.extractOutboundAddress(config), 'old.example.com');
    });

    test('reads classic servers address for trojan', () {
      final config = {
        'outbounds': [
          {
            'protocol': 'trojan',
            'settings': {
              'servers': [
                {'address': 'trojan.example.com', 'port': 443, 'password': 'x'},
              ],
            },
          },
        ],
      };

      expect(manager.extractOutboundAddress(config), 'trojan.example.com');
    });
  });

  group('createModifiedConfig', () {
    test('rewrites flattened settings.address without inventing vnext', () {
      final config = {
        'inbounds': [
          {'protocol': 'socks', 'port': 10808},
        ],
        'outbounds': [
          {
            'tag': 'proxy',
            'protocol': 'vless',
            'settings': {
              'address': 'pp.parsaoo.ir',
              'port': 443,
              'id': '1da0fcb1-28f8-44f4-ae97-7387b90ebda2',
            },
          },
        ],
      };

      final modified = manager.createModifiedConfig(config, 20000, '1.2.3.4');
      final outbound = (modified['outbounds'] as List).first as Map;
      final settings = outbound['settings'] as Map;

      expect(modified['inbounds'][0]['port'], 20000);
      expect(settings['address'], '1.2.3.4');
      expect(settings.containsKey('vnext'), isFalse);
      expect(settings['id'], '1da0fcb1-28f8-44f4-ae97-7387b90ebda2');
    });

    test('rewrites classic vnext address', () {
      final config = {
        'inbounds': [
          {'protocol': 'http', 'port': 10809},
        ],
        'outbounds': [
          {
            'protocol': 'vmess',
            'settings': {
              'vnext': [
                {
                  'address': 'old.example.com',
                  'port': 443,
                  'users': [
                    {'id': 'uuid'},
                  ],
                },
              ],
            },
          },
        ],
      };

      final modified = manager.createModifiedConfig(config, 30000, '9.9.9.9');
      final vnext = modified['outbounds'][0]['settings']['vnext'] as List;

      expect(vnext[0]['address'], '9.9.9.9');
    });

    test('rewrites ext geo dat refs onto bundled geoip/geosite', () {
      final config = {
        'inbounds': [
          {'protocol': 'socks', 'port': 10808},
        ],
        'dns': {
          'servers': [
            {
              'address': '223.5.5.5',
              'domains': ['ext:geosite-ir.dat:ir'],
            },
          ],
        },
        'outbounds': [
          {
            'tag': 'proxy',
            'protocol': 'vless',
            'settings': {
              'vnext': [
                {'address': 'example.com', 'port': 443},
              ],
            },
          },
        ],
        'routing': {
          'rules': [
            {
              'type': 'field',
              'ip': ['ext:geoip-only-cn-private.dat:private'],
              'outboundTag': 'direct',
            },
            {
              'type': 'field',
              'domain': ['geosite:private', 'ext:custom-geosite.dat:google'],
              'outboundTag': 'direct',
            },
          ],
        },
      };

      final modified = manager.createModifiedConfig(config, 20000, '1.2.3.4');
      final rules = modified['routing']['rules'] as List;
      final dnsServer = modified['dns']['servers'][0] as Map;

      expect(rules[0]['ip'], ['geoip:private']);
      expect(rules[1]['domain'], ['geosite:private', 'geosite:google']);
      expect(dnsServer['domains'], ['geosite:ir']);
    });
  });
}
