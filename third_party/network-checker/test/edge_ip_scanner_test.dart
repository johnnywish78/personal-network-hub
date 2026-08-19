import 'package:flutter_test/flutter_test.dart';
import 'package:rdnbenet/core/services/edge_ip_scanner.dart';

void main() {
  group('EdgeIpScanner IP Input Parsing Tests', () {
    test('parses single IPs without ports correctly', () {
      final input = '1.1.1.1\n8.8.8.8';
      final parsed = EdgeIpScanner.parseIpInput(input);
      expect(parsed, equals(['1.1.1.1', '8.8.8.8']));
    });

    test('parses single IPs with custom ports correctly', () {
      final input = '1.1.1.1:8443\n8.8.8.8:8080\n9.9.9.9';
      final parsed = EdgeIpScanner.parseIpInput(input);
      expect(parsed, equals(['1.1.1.1:8443', '8.8.8.8:8080', '9.9.9.9']));
    });

    test('ignores invalid IPs or invalid ports', () {
      final input = '1.1.1.1:999999\n8.8.8.8:abc\n256.0.0.1\n1.1.1.1:80';
      final parsed = EdgeIpScanner.parseIpInput(input);
      // Only 1.1.1.1:80 is valid out of these
      expect(parsed, equals(['1.1.1.1:80']));
    });

    test('parses CIDR ranges and mixes them with custom port IPs', () {
      final input = '192.168.1.0/30\n1.1.1.1:443';
      final parsed = EdgeIpScanner.parseIpInput(input);
      expect(parsed, equals(['192.168.1.1', '192.168.1.2', '1.1.1.1:443']));
    });
  });
}
