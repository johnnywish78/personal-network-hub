import 'package:flutter_test/flutter_test.dart';
import 'package:rdnbenet/core/services/cdn_config_scanner.dart';
import 'package:rdnbenet/features/cdn_config_scan/data/cdn_scan_presets.dart';

void main() {
  group('cdnScanPresets', () {
    test('includes Cloudflare, Fastly, and the added CDN providers', () {
      final names = cdnScanPresets.map((p) => p.name).toList();
      expect(names.toSet().length, names.length);
      expect(names, containsAll([
        'Cloudflare',
        'Fastly',
        'Amazon CloudFront',
        'Gcore',
        'CDNvideo',
        'Alibaba Cloud CDN',
        'Tencent Cloud CDN',
        'CDN77',
        'Edgio',
        'Bunny.net',
        'KeyCDN',
        'CacheFly',
        'Azure CDN / Front Door',
        'Google Cloud CDN',
        'Imperva / Incapsula',
        'Leaseweb CDN',
        'Baidu AI Cloud CDN',
      ]));
    });

    test('every preset pastes at least one CIDR or IP', () {
      for (final preset in cdnScanPresets) {
        expect(preset.cidrs.trim(), isNotEmpty, reason: preset.name);
      }
    });
  });

  group('CdnConfigScanner.parseIpInput', () {
    test('expands small CIDRs fully', () {
      final parsed = CdnConfigScanner.parseIpInput('192.168.1.0/30');
      expect(parsed, ['192.168.1.1', '192.168.1.2']);
    });

    test('samples wide CIDRs instead of expanding every host', () {
      final parsed = CdnConfigScanner.parseIpInput('10.0.0.0/16');
      expect(parsed.length, 4096);
      expect(parsed.first, '10.0.0.1');
      expect(parsed.toSet().length, parsed.length);
    });
  });
}
