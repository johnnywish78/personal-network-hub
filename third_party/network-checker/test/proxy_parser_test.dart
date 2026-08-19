import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:rdnbenet/core/services/proxy_parser_service.dart';

void main() {
  group('ProxyParserService Tests', () {
    test('parses VLESS share link correctly', () {
      const link =
          'vless://00000000-0000-0000-0000-000000000001@entry.example.com:443?type=ws&security=tls&path=%2Fentry-path&sni=entry.example.com#MyEntry';
      final node = ProxyParserService.parseLink(link);

      expect(node.protocol, equals('vless'));
      expect(node.address, equals('entry.example.com'));
      expect(node.port, equals(443));
      expect(node.idOrPassword, equals('00000000-0000-0000-0000-000000000001'));
      expect(node.network, equals('ws'));
      expect(node.security, equals('tls'));
      expect(node.path, equals('/entry-path'));
      expect(node.sni, equals('entry.example.com'));
      expect(node.remarks, equals('MyEntry'));
    });

    test('parses Trojan share link correctly', () {
      const link =
          'trojan://mysecretpass@exit.example.com:8443?security=tls&sni=exit.example.com&type=grpc&serviceName=mygrpc#MyTrojan';
      final node = ProxyParserService.parseLink(link);

      expect(node.protocol, equals('trojan'));
      expect(node.address, equals('exit.example.com'));
      expect(node.port, equals(8443));
      expect(node.idOrPassword, equals('mysecretpass'));
      expect(node.network, equals('grpc'));
      expect(node.security, equals('tls'));
      expect(node.serviceName, equals('mygrpc'));
      expect(node.remarks, equals('MyTrojan'));
    });

    test('parses VMess base64 JSON share link correctly', () {
      final vmessJson = {
        'v': '2',
        'ps': 'VMessExit',
        'add': 'vmess.example.com',
        'port': 2096,
        'id': '00000000-0000-0000-0000-000000000002',
        'aid': 0,
        'scy': 'auto',
        'net': 'ws',
        'path': '/vmess-ws',
        'tls': 'tls',
        'sni': 'vmess.example.com'
      };
      final base64Str = base64.encode(utf8.encode(json.encode(vmessJson)));
      final link = 'vmess://$base64Str';

      final node = ProxyParserService.parseLink(link);

      expect(node.protocol, equals('vmess'));
      expect(node.address, equals('vmess.example.com'));
      expect(node.port, equals(2096));
      expect(node.idOrPassword, equals('00000000-0000-0000-0000-000000000002'));
      expect(node.network, equals('ws'));
      expect(node.security, equals('tls'));
      expect(node.path, equals('/vmess-ws'));
      expect(node.remarks, equals('VMessExit'));
    });

    test('parses Shadowsocks share link correctly', () {
      final userinfoBase64 = base64.encode(utf8.encode('chacha20-ietf-poly1305:secretpass'));
      final link = 'ss://$userinfoBase64@ss.example.com:8388#SSNode';
      final node = ProxyParserService.parseLink(link);

      expect(node.protocol, equals('shadowsocks'));
      expect(node.address, equals('ss.example.com'));
      expect(node.port, equals(8388));
      expect(node.cipher, equals('chacha20-ietf-poly1305'));
      expect(node.idOrPassword, equals('secretpass'));
      expect(node.remarks, equals('SSNode'));

      final outbound = node.toXrayOutbound(tag: 'hop0');
      expect(outbound['protocol'], equals('shadowsocks'));
      final servers = outbound['settings']['servers'] as List;
      expect(servers.first['method'], equals('chacha20-ietf-poly1305'));
      expect(servers.first['password'], equals('secretpass'));
    });

    test('parses SOCKS share link correctly', () {
      const link = 'socks5://admin:p%40ss123@socks.example.com:1080#SocksNode';
      final node = ProxyParserService.parseLink(link);

      expect(node.protocol, equals('socks'));
      expect(node.address, equals('socks.example.com'));
      expect(node.port, equals(1080));
      expect(node.idOrPassword, equals('admin'));
      expect(node.encryption, equals('p@ss123'));
      expect(node.remarks, equals('SocksNode'));

      final outbound = node.toXrayOutbound(tag: 'hop0');
      expect(outbound['protocol'], equals('socks'));
      final servers = outbound['settings']['servers'] as List;
      final users = servers.first['users'] as List;
      expect(users.first['user'], equals('admin'));
      expect(users.first['pass'], equals('p@ss123'));
    });

    test('parses HTTP/HTTPS share link correctly', () {
      const link = 'https://user:pass@proxy.example.com:8443?sni=proxy.example.com#HttpsNode';
      final node = ProxyParserService.parseLink(link);

      expect(node.protocol, equals('http'));
      expect(node.address, equals('proxy.example.com'));
      expect(node.port, equals(8443));
      expect(node.security, equals('tls'));
      expect(node.sni, equals('proxy.example.com'));
      expect(node.remarks, equals('HttpsNode'));

      final outbound = node.toXrayOutbound(tag: 'hop0');
      expect(outbound['protocol'], equals('http'));
      expect(outbound['streamSettings']['security'], equals('tls'));
    });

    test('generates multi-hop profile with mixed protocols (SS -> SOCKS -> VLESS)', () {
      final ssLink = 'ss://${base64.encode(utf8.encode("aes-256-gcm:pass"))}@1.1.1.1:8388#EntrySS';
      const socksLink = 'socks5://user:pass@2.2.2.2:1080#MiddleSocks';
      const vlessLink = 'vless://uuid@3.3.3.3:443?security=tls#ExitVless';

      final profile = ProxyParserService.generateChainProfile(
        nodeShareLinks: [ssLink, socksLink, vlessLink],
      );

      expect(profile['remarks'], contains('SHADOWSOCKS (Entry) → VLESS (Exit)'));

      final outbounds = profile['outbounds'] as List;
      expect(outbounds.length, equals(5)); // hop0, hop1, hop2, direct, block
      expect(outbounds[0]['protocol'], equals('shadowsocks'));
      expect(outbounds[1]['protocol'], equals('socks'));
      expect(outbounds[1]['streamSettings']['sockopt']['dialerProxy'], equals('hop0'));
      expect(outbounds[2]['protocol'], equals('vless'));
      expect(outbounds[2]['streamSettings']['sockopt']['dialerProxy'], equals('hop1'));
    });

    test('throws FormatException when less than 2 links are provided', () {
      expect(
        () => ProxyParserService.generateChainProfile(nodeShareLinks: ['vless://uuid@host:443']),
        throwsFormatException,
      );
    });

    test('throws FormatException on unsupported protocol link', () {
      expect(
        () => ProxyParserService.parseLink('ftp://1.1.1.1:21'),
        throwsFormatException,
      );
    });
  });
}
