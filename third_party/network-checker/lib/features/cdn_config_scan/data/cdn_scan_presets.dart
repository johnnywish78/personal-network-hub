import '../../edge_ip_checker/cf_ip_ranges.dart';

/// A named CIDR list that can be pasted into CDN Config Scan.
class CdnScanPreset {
  final String name;
  final String cidrs;

  const CdnScanPreset({
    required this.name,
    required this.cidrs,
  });
}

String _cidrs(List<String> ranges) => ranges.join('\n');

/// Cloudflare's bundled list is thousands of /24s. Expanding every host would
/// create millions of xray tests, so the preset uses the first usable IP in
/// each range. Other presets keep their CIDR text and are sampled by the parser.
String _firstUsableHosts(String ranges) {
  final hosts = <String>[];
  for (final raw in ranges.split('\n')) {
    final line = raw.trim();
    if (line.isEmpty || line.startsWith('#')) continue;
    if (!line.contains('/')) {
      hosts.add(line);
      continue;
    }
    final ip = line.split('/').first;
    final octets = ip.split('.');
    if (octets.length != 4) continue;
    final last = int.tryParse(octets[3]);
    if (last == null) continue;
    octets[3] = '${(last + 1).clamp(0, 255)}';
    hosts.add(octets.join('.'));
  }
  return hosts.join('\n');
}

/// Built-in CDN IP presets for the scan IP step.
final List<CdnScanPreset> cdnScanPresets = [
  CdnScanPreset(name: 'Cloudflare', cidrs: _firstUsableHosts(cloudflareIpRanges)),
  CdnScanPreset(name: 'Fastly', cidrs: fastlyIpRanges.trim()),
  CdnScanPreset(
    name: 'Amazon CloudFront',
    cidrs: _cidrs(const [
      '13.32.0.0/15',
      '13.35.0.0/16',
      '13.224.0.0/14',
      '13.249.0.0/16',
      '18.64.0.0/14',
      '52.84.0.0/15',
      '54.192.0.0/16',
      '54.230.0.0/16',
      '54.239.128.0/18',
      '54.240.128.0/18',
      '64.252.64.0/18',
      '99.84.0.0/16',
      '99.86.0.0/16',
      '143.204.0.0/16',
      '204.246.164.0/22',
    ]),
  ),
  CdnScanPreset(
    name: 'Gcore',
    cidrs: _cidrs(const [
      '92.223.64.0/18',
      '92.38.128.0/17',
      '185.156.176.0/22',
      '185.178.208.0/22',
      '185.187.240.0/22',
      '185.228.168.0/22',
      '188.116.12.0/22',
      '195.201.200.0/22',
    ]),
  ),
  CdnScanPreset(
    name: 'CDNvideo',
    cidrs: _cidrs(const [
      '89.111.160.0/19',
      '91.226.136.0/22',
      '94.198.52.0/22',
      '185.45.192.0/22',
      '185.129.100.0/22',
      '194.85.80.0/21',
    ]),
  ),
  CdnScanPreset(
    name: 'Alibaba Cloud CDN',
    cidrs: _cidrs(const [
      '47.74.0.0/15',
      '47.88.0.0/14',
      '47.246.0.0/16',
      '106.11.0.0/16',
      '140.205.0.0/16',
      '163.181.0.0/16',
    ]),
  ),
  CdnScanPreset(
    name: 'Tencent Cloud CDN',
    cidrs: _cidrs(const [
      '43.128.0.0/14',
      '43.132.0.0/14',
      '129.226.0.0/16',
      '150.109.0.0/16',
      '162.14.0.0/16',
      '203.205.128.0/17',
    ]),
  ),
  CdnScanPreset(
    name: 'CDN77',
    cidrs: _cidrs(const [
      '84.17.32.0/19',
      '89.187.160.0/19',
      '185.59.220.0/22',
      '185.152.64.0/22',
      '185.229.224.0/22',
      '195.181.160.0/19',
    ]),
  ),
  CdnScanPreset(
    name: 'Edgio',
    cidrs: _cidrs(const [
      '68.142.64.0/18',
      '69.28.128.0/18',
      '72.21.80.0/20',
      '93.184.216.0/21',
      '152.195.0.0/16',
      '192.16.64.0/18',
      '208.111.128.0/17',
    ]),
  ),
  CdnScanPreset(
    name: 'Bunny.net',
    cidrs: _cidrs(const [
      '38.92.173.0/24',
      '91.200.176.0/24',
      '103.180.114.0/24',
      '103.180.115.0/24',
      '107.150.176.0/24',
      '109.104.146.0/24',
      '109.224.228.0/23',
      '185.190.83.0/24',
      '194.156.156.0/24',
      '212.104.158.0/24',
    ]),
  ),
  CdnScanPreset(
    name: 'KeyCDN',
    cidrs: _cidrs(const [
      '68.70.192.0/24',
      '68.70.193.0/24',
      '68.70.194.0/24',
      '68.70.205.0/24',
    ]),
  ),
  CdnScanPreset(
    name: 'CacheFly',
    cidrs: _cidrs(const [
      '45.88.132.0/22',
      '204.93.142.0/24',
      '204.93.143.0/24',
      '205.234.175.0/24',
    ]),
  ),
  CdnScanPreset(
    name: 'Azure CDN / Front Door',
    cidrs: _cidrs(const [
      '13.107.246.0/24',
      '13.107.247.0/24',
      '13.107.21.0/24',
      '13.107.42.0/24',
      '13.107.226.0/24',
      '150.171.0.0/16',
    ]),
  ),
  CdnScanPreset(
    name: 'Google Cloud CDN',
    cidrs: _cidrs(const [
      '34.96.0.0/14',
      '34.104.0.0/14',
      '34.110.0.0/15',
      '34.120.0.0/14',
      '34.160.0.0/11',
    ]),
  ),
  CdnScanPreset(
    name: 'Imperva / Incapsula',
    cidrs: _cidrs(const [
      '199.83.128.0/21',
      '198.143.32.0/19',
      '149.126.72.0/21',
      '103.28.248.0/22',
      '185.11.124.0/22',
      '192.230.64.0/18',
      '45.64.64.0/22',
      '107.154.0.0/16',
    ]),
  ),
  CdnScanPreset(
    name: 'Leaseweb CDN',
    cidrs: _cidrs(const [
      '178.162.216.0/22',
      '178.162.220.0/22',
      '46.166.184.0/22',
      '37.58.64.0/19',
    ]),
  ),
  CdnScanPreset(
    name: 'Baidu AI Cloud CDN',
    cidrs: _cidrs(const [
      '180.76.0.0/16',
      '106.12.0.0/15',
      '182.61.0.0/16',
      '220.181.0.0/16',
    ]),
  ),
];
