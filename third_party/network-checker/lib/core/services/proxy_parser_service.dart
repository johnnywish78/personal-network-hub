import 'dart:convert';

/// Data model representing parsed proxy details
class ParsedProxyNode {
  final String protocol; // 'vless', 'vmess', 'trojan', 'shadowsocks', 'socks', 'http'
  final String address;
  final int port;
  final String? idOrPassword;
  final String? alterId;
  final String? cipher;
  final String network; // 'tcp', 'ws', 'grpc', 'h2', 'kcp', 'quic'
  final String security; // 'none', 'tls', 'reality'
  final String? sni;
  final String? path;
  final String? host;
  final String? serviceName;
  final String? mode;
  final String? publicKey;
  final String? shortId;
  final String? spiderX;
  final String? fingerprint;
  final String? flow;
  final String? encryption;
  final List<String>? alpn;
  final String? headerType;
  final String remarks;

  ParsedProxyNode({
    required this.protocol,
    required this.address,
    required this.port,
    this.idOrPassword,
    this.alterId,
    this.cipher,
    this.network = 'tcp',
    this.security = 'none',
    this.sni,
    this.path,
    this.host,
    this.serviceName,
    this.mode,
    this.publicKey,
    this.shortId,
    this.spiderX,
    this.fingerprint,
    this.flow,
    this.encryption,
    this.alpn,
    this.headerType,
    required this.remarks,
  });

  /// Converts parsed proxy node to Xray outbound map
  Map<String, dynamic> toXrayOutbound({
    required String tag,
    String? dialerProxyTag,
  }) {
    final Map<String, dynamic> outbound = {
      'tag': tag,
      'protocol': protocol,
    };

    // Protocol settings
    if (protocol == 'vless') {
      final userMap = <String, dynamic>{
        'id': idOrPassword ?? '',
        'encryption': (encryption != null && encryption!.isNotEmpty) ? encryption : 'none',
      };
      if (flow != null && flow!.isNotEmpty) {
        userMap['flow'] = flow;
      }

      outbound['settings'] = {
        'vnext': [
          {
            'address': address,
            'port': port,
            'users': [userMap],
          }
        ],
      };
    } else if (protocol == 'vmess') {
      int parsedAlterId = 0;
      if (alterId != null) {
        parsedAlterId = int.tryParse(alterId!) ?? 0;
      }
      outbound['settings'] = {
        'vnext': [
          {
            'address': address,
            'port': port,
            'users': [
              {
                'id': idOrPassword ?? '',
                'alterId': parsedAlterId,
                'security': (cipher != null && cipher!.isNotEmpty) ? cipher : 'auto',
              }
            ],
          }
        ],
      };
    } else if (protocol == 'trojan') {
      outbound['settings'] = {
        'servers': [
          {
            'address': address,
            'port': port,
            'password': idOrPassword ?? '',
          }
        ],
      };
    } else if (protocol == 'shadowsocks') {
      outbound['settings'] = {
        'servers': [
          {
            'address': address,
            'port': port,
            'method': (cipher != null && cipher!.isNotEmpty) ? cipher : 'aes-256-gcm',
            'password': idOrPassword ?? '',
          }
        ],
      };
    } else if (protocol == 'socks') {
      final userList = <Map<String, dynamic>>[];
      if (idOrPassword != null && idOrPassword!.isNotEmpty) {
        userList.add({
          'user': idOrPassword,
          'pass': encryption ?? '',
        });
      }
      outbound['settings'] = {
        'servers': [
          {
            'address': address,
            'port': port,
            'users': userList,
          }
        ],
      };
    } else if (protocol == 'http') {
      final userList = <Map<String, dynamic>>[];
      if (idOrPassword != null && idOrPassword!.isNotEmpty) {
        userList.add({
          'user': idOrPassword,
          'pass': encryption ?? '',
        });
      }
      outbound['settings'] = {
        'servers': [
          {
            'address': address,
            'port': port,
            'users': userList,
          }
        ],
      };
    } else {
      throw FormatException('Unsupported protocol: $protocol');
    }

    // Stream settings
    final Map<String, dynamic> streamSettings = {
      'network': network,
      'security': security,
    };

    if (security == 'tls') {
      final Map<String, dynamic> tlsSettings = {};
      if (sni != null && sni!.isNotEmpty) {
        tlsSettings['serverName'] = sni;
      }
      if (alpn != null && alpn!.isNotEmpty) {
        tlsSettings['alpn'] = alpn;
      }
      if (fingerprint != null && fingerprint!.isNotEmpty) {
        tlsSettings['fingerprint'] = fingerprint;
      }
      streamSettings['tlsSettings'] = tlsSettings;
    } else if (security == 'reality') {
      final Map<String, dynamic> realitySettings = {};
      if (sni != null && sni!.isNotEmpty) {
        realitySettings['serverName'] = sni;
      }
      if (publicKey != null && publicKey!.isNotEmpty) {
        realitySettings['publicKey'] = publicKey;
      }
      if (shortId != null && shortId!.isNotEmpty) {
        realitySettings['shortId'] = shortId;
      }
      if (spiderX != null && spiderX!.isNotEmpty) {
        realitySettings['spiderX'] = spiderX;
      }
      if (fingerprint != null && fingerprint!.isNotEmpty) {
        realitySettings['fingerprint'] = fingerprint;
      }
      streamSettings['realitySettings'] = realitySettings;
    }

    // Transport settings
    if (network == 'ws') {
      final Map<String, dynamic> wsSettings = {};
      if (path != null && path!.isNotEmpty) {
        wsSettings['path'] = path;
      }
      if (host != null && host!.isNotEmpty) {
        wsSettings['headers'] = {'Host': host};
      }
      streamSettings['wsSettings'] = wsSettings;
    } else if (network == 'grpc') {
      final Map<String, dynamic> grpcSettings = {};
      if (serviceName != null && serviceName!.isNotEmpty) {
        grpcSettings['serviceName'] = serviceName;
      }
      if (mode == 'multi') {
        grpcSettings['multiMode'] = true;
      }
      streamSettings['grpcSettings'] = grpcSettings;
    } else if (network == 'h2' || network == 'http') {
      final Map<String, dynamic> httpSettings = {};
      if (path != null && path!.isNotEmpty) {
        httpSettings['path'] = path;
      }
      if (host != null && host!.isNotEmpty) {
        httpSettings['host'] = [host];
      }
      streamSettings['httpSettings'] = httpSettings;
    } else if (network == 'kcp') {
      final Map<String, dynamic> kcpSettings = {};
      if (headerType != null && headerType!.isNotEmpty) {
        kcpSettings['header'] = {'type': headerType};
      }
      streamSettings['kcpSettings'] = kcpSettings;
    } else if (network == 'quic') {
      final Map<String, dynamic> quicSettings = {};
      if (headerType != null && headerType!.isNotEmpty) {
        quicSettings['header'] = {'type': headerType};
      }
      streamSettings['quicSettings'] = quicSettings;
    }

    // Dialer proxy (multi-hop chaining)
    if (dialerProxyTag != null && dialerProxyTag.isNotEmpty) {
      streamSettings['sockopt'] = {
        'dialerProxy': dialerProxyTag,
      };
    }

    outbound['streamSettings'] = streamSettings;
    return outbound;
  }
}

/// Service to parse proxy share links and assemble multi-hop Xray JSON configs
class ProxyParserService {
  /// Parses a proxy link (VLESS, VMess, Trojan, SS, SOCKS, HTTP) into a [ParsedProxyNode]
  static ParsedProxyNode parseLink(String shareLink) {
    final trimmed = shareLink.trim();
    if (trimmed.isEmpty) {
      throw const FormatException('Share link cannot be empty');
    }

    if (trimmed.startsWith('vless://')) {
      return _parseVless(trimmed);
    } else if (trimmed.startsWith('vmess://')) {
      return _parseVmess(trimmed);
    } else if (trimmed.startsWith('trojan://')) {
      return _parseTrojan(trimmed);
    } else if (trimmed.startsWith('ss://')) {
      return _parseShadowsocks(trimmed);
    } else if (trimmed.startsWith('socks://') || trimmed.startsWith('socks5://')) {
      return _parseSocks(trimmed);
    } else if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return _parseHttp(trimmed);
    } else {
      throw const FormatException(
        'Unsupported proxy link protocol. Supported protocols: vless://, vmess://, trojan://, ss://, socks://, socks5://, http://, https://',
      );
    }
  }

  /// Parse vless:// link
  static ParsedProxyNode _parseVless(String link) {
    // Format: vless://uuid@host:port?query#remarks
    final uriStr = link.substring(8);
    final fragmentParts = uriStr.split('#');
    final remarks = fragmentParts.length > 1 ? Uri.decodeComponent(fragmentParts[1]) : 'VLESS Node';
    final beforeFragment = fragmentParts[0];

    final queryParts = beforeFragment.split('?');
    final queryString = queryParts.length > 1 ? queryParts[1] : '';
    final mainPart = queryParts[0];

    final atParts = mainPart.split('@');
    if (atParts.length != 2) {
      throw const FormatException('Invalid VLESS format: missing "@" separating UUID and host');
    }

    final uuid = atParts[0];
    final hostPortStr = atParts[1];

    final hostPort = _parseHostPort(hostPortStr);
    final queryParams = _parseQueryString(queryString);

    final net = queryParams['type'] ?? queryParams['network'] ?? 'tcp';
    final sec = queryParams['security'] ?? 'none';
    final sni = queryParams['sni'] ?? queryParams['peer'];
    final path = queryParams['path'] != null ? Uri.decodeComponent(queryParams['path']!) : null;
    final host = queryParams['host'] ?? queryParams['headerType'];
    final serviceName = queryParams['serviceName'];
    final mode = queryParams['mode'];
    final pbk = queryParams['pbk'] ?? queryParams['publicKey'];
    final sid = queryParams['sid'] ?? queryParams['shortId'];
    final spx = queryParams['spx'] ?? queryParams['spiderX'];
    final fp = queryParams['fp'] ?? queryParams['fingerprint'];
    final flow = queryParams['flow'];
    final encryption = queryParams['encryption'];
    final alpnStr = queryParams['alpn'];
    final alpn = alpnStr != null ? alpnStr.split(',') : null;
    final headerType = queryParams['headerType'];

    return ParsedProxyNode(
      protocol: 'vless',
      address: hostPort.host,
      port: hostPort.port,
      idOrPassword: uuid,
      network: net,
      security: sec,
      sni: sni,
      path: path,
      host: host,
      serviceName: serviceName,
      mode: mode,
      publicKey: pbk,
      shortId: sid,
      spiderX: spx,
      fingerprint: fp,
      flow: flow,
      encryption: encryption,
      alpn: alpn,
      headerType: headerType,
      remarks: remarks.isNotEmpty ? remarks : 'VLESS Node',
    );
  }

  /// Parse trojan:// link
  static ParsedProxyNode _parseTrojan(String link) {
    // Format: trojan://password@host:port?query#remarks
    final uriStr = link.substring(9);
    final fragmentParts = uriStr.split('#');
    final remarks = fragmentParts.length > 1 ? Uri.decodeComponent(fragmentParts[1]) : 'Trojan Node';
    final beforeFragment = fragmentParts[0];

    final queryParts = beforeFragment.split('?');
    final queryString = queryParts.length > 1 ? queryParts[1] : '';
    final mainPart = queryParts[0];

    final atParts = mainPart.split('@');
    if (atParts.length != 2) {
      throw const FormatException('Invalid Trojan format: missing "@" separating password and host');
    }

    final password = Uri.decodeComponent(atParts[0]);
    final hostPortStr = atParts[1];

    final hostPort = _parseHostPort(hostPortStr);
    final queryParams = _parseQueryString(queryString);

    final net = queryParams['type'] ?? queryParams['network'] ?? 'tcp';
    final sec = queryParams['security'] ?? 'tls';
    final sni = queryParams['sni'] ?? queryParams['peer'] ?? queryParams['host'];
    final path = queryParams['path'] != null ? Uri.decodeComponent(queryParams['path']!) : null;
    final host = queryParams['host'];
    final serviceName = queryParams['serviceName'];
    final mode = queryParams['mode'];
    final pbk = queryParams['pbk'] ?? queryParams['publicKey'];
    final sid = queryParams['sid'] ?? queryParams['shortId'];
    final spx = queryParams['spx'] ?? queryParams['spiderX'];
    final fp = queryParams['fp'] ?? queryParams['fingerprint'];
    final alpnStr = queryParams['alpn'];
    final alpn = alpnStr != null ? alpnStr.split(',') : null;
    final headerType = queryParams['headerType'];

    return ParsedProxyNode(
      protocol: 'trojan',
      address: hostPort.host,
      port: hostPort.port,
      idOrPassword: password,
      network: net,
      security: sec,
      sni: sni,
      path: path,
      host: host,
      serviceName: serviceName,
      mode: mode,
      publicKey: pbk,
      shortId: sid,
      spiderX: spx,
      fingerprint: fp,
      alpn: alpn,
      headerType: headerType,
      remarks: remarks.isNotEmpty ? remarks : 'Trojan Node',
    );
  }

  /// Parse vmess:// link (base64 JSON or URI fallback)
  static ParsedProxyNode _parseVmess(String link) {
    final raw = link.substring(8).trim();

    // Check if it's base64 encoded JSON
    if (!raw.contains('@')) {
      try {
        final decodedStr = utf8.decode(base64.decode(_normalizeBase64(raw)));
        final Map<String, dynamic> jsonMap = json.decode(decodedStr);

        final add = jsonMap['add']?.toString() ?? '';
        final port = int.tryParse(jsonMap['port']?.toString() ?? '') ?? 443;
        final id = jsonMap['id']?.toString() ?? '';
        final aid = jsonMap['aid']?.toString() ?? '0';
        final scy = jsonMap['scy']?.toString() ?? jsonMap['cipher']?.toString() ?? 'auto';
        final net = jsonMap['net']?.toString() ?? 'tcp';
        final sec = (jsonMap['tls']?.toString() == 'tls' || jsonMap['tls']?.toString() == '1')
            ? 'tls'
            : (jsonMap['tls']?.toString() == 'reality' ? 'reality' : 'none');
        final path = jsonMap['path']?.toString();
        final host = jsonMap['host']?.toString();
        final sni = jsonMap['sni']?.toString() ?? host;
        final ps = jsonMap['ps']?.toString() ?? 'VMess Node';
        final alpnStr = jsonMap['alpn']?.toString();
        final alpn = alpnStr != null && alpnStr.isNotEmpty ? alpnStr.split(',') : null;
        final fp = jsonMap['fp']?.toString();
        final headerType = jsonMap['type']?.toString();

        if (add.isEmpty || id.isEmpty) {
          throw const FormatException('VMess JSON missing address or id');
        }

        return ParsedProxyNode(
          protocol: 'vmess',
          address: add,
          port: port,
          idOrPassword: id,
          alterId: aid,
          cipher: scy,
          network: net,
          security: sec,
          sni: sni,
          path: path,
          host: host,
          fingerprint: fp,
          alpn: alpn,
          headerType: headerType,
          remarks: ps.isNotEmpty ? ps : 'VMess Node',
        );
      } catch (e) {
        if (e is FormatException && e.message.startsWith('Unsupported')) rethrow;
        // Fallthrough to URI style parse if base64 fails
      }
    }

    // URI format fallback: vmess://uuid@host:port?query#remarks
    final fragmentParts = raw.split('#');
    final remarks = fragmentParts.length > 1 ? Uri.decodeComponent(fragmentParts[1]) : 'VMess Node';
    final beforeFragment = fragmentParts[0];

    final queryParts = beforeFragment.split('?');
    final queryString = queryParts.length > 1 ? queryParts[1] : '';
    final mainPart = queryParts[0];

    final atParts = mainPart.split('@');
    if (atParts.length != 2) {
      throw const FormatException('Invalid VMess URI format: missing "@" separating UUID and host');
    }

    final uuid = atParts[0];
    final hostPortStr = atParts[1];

    final hostPort = _parseHostPort(hostPortStr);
    final queryParams = _parseQueryString(queryString);

    final net = queryParams['net'] ?? queryParams['type'] ?? queryParams['network'] ?? 'tcp';
    final sec = queryParams['security'] ?? queryParams['tls'] ?? 'none';
    final sni = queryParams['sni'] ?? queryParams['peer'] ?? queryParams['host'];
    final path = queryParams['path'] != null ? Uri.decodeComponent(queryParams['path']!) : null;
    final host = queryParams['host'];
    final fp = queryParams['fp'] ?? queryParams['fingerprint'];
    final aid = queryParams['aid'] ?? queryParams['alterId'] ?? '0';
    final cipher = queryParams['scy'] ?? queryParams['cipher'] ?? 'auto';

    return ParsedProxyNode(
      protocol: 'vmess',
      address: hostPort.host,
      port: hostPort.port,
      idOrPassword: uuid,
      alterId: aid,
      cipher: cipher,
      network: net,
      security: sec,
      sni: sni,
      path: path,
      host: host,
      fingerprint: fp,
      remarks: remarks.isNotEmpty ? remarks : 'VMess Node',
    );
  }

  /// Parse ss:// (Shadowsocks) link
  static ParsedProxyNode _parseShadowsocks(String link) {
    final uriStr = link.substring(5);
    final fragmentParts = uriStr.split('#');
    final remarks = fragmentParts.length > 1 ? Uri.decodeComponent(fragmentParts[1]) : 'Shadowsocks Node';
    final beforeFragment = fragmentParts[0];

    final queryParts = beforeFragment.split('?');
    final queryString = queryParts.length > 1 ? queryParts[1] : '';
    final mainPart = queryParts[0];

    String method = '';
    String password = '';
    String host = '';
    int port = 8388;

    if (mainPart.contains('@')) {
      final atParts = mainPart.split('@');
      final userinfo = atParts[0];
      final hostPortStr = atParts[1];

      final hostPort = _parseHostPort(hostPortStr);
      host = hostPort.host;
      port = hostPort.port;

      String decodedUserinfo = userinfo;
      if (!userinfo.contains(':')) {
        try {
          decodedUserinfo = utf8.decode(base64.decode(_normalizeBase64(userinfo)));
        } catch (_) {}
      }

      final colonIdx = decodedUserinfo.indexOf(':');
      if (colonIdx != -1) {
        method = Uri.decodeComponent(decodedUserinfo.substring(0, colonIdx));
        password = Uri.decodeComponent(decodedUserinfo.substring(colonIdx + 1));
      } else {
        password = Uri.decodeComponent(decodedUserinfo);
      }
    } else {
      // Legacy base64 format: ss://BASE64(method:password@host:port)
      try {
        final decodedStr = utf8.decode(base64.decode(_normalizeBase64(mainPart)));
        final atParts = decodedStr.split('@');
        if (atParts.length == 2) {
          final userinfo = atParts[0];
          final hostPortStr = atParts[1];
          final hostPort = _parseHostPort(hostPortStr);
          host = hostPort.host;
          port = hostPort.port;

          final colonIdx = userinfo.indexOf(':');
          if (colonIdx != -1) {
            method = Uri.decodeComponent(userinfo.substring(0, colonIdx));
            password = Uri.decodeComponent(userinfo.substring(colonIdx + 1));
          } else {
            password = Uri.decodeComponent(userinfo);
          }
        } else {
          throw const FormatException('Invalid Shadowsocks format');
        }
      } catch (e) {
        throw FormatException('Invalid Shadowsocks format: $e');
      }
    }

    final queryParams = _parseQueryString(queryString);
    final plugin = queryParams['plugin'];

    return ParsedProxyNode(
      protocol: 'shadowsocks',
      address: host,
      port: port,
      idOrPassword: password,
      cipher: method.isNotEmpty ? method : 'aes-256-gcm',
      remarks: remarks.isNotEmpty ? remarks : 'Shadowsocks Node',
    );
  }

  /// Parse socks:// or socks5:// link
  static ParsedProxyNode _parseSocks(String link) {
    final prefixLen = link.startsWith('socks5://') ? 9 : 8;
    final uriStr = link.substring(prefixLen);
    final fragmentParts = uriStr.split('#');
    final remarks = fragmentParts.length > 1 ? Uri.decodeComponent(fragmentParts[1]) : 'SOCKS Node';
    final beforeFragment = fragmentParts[0];

    final queryParts = beforeFragment.split('?');
    final queryString = queryParts.length > 1 ? queryParts[1] : '';
    final mainPart = queryParts[0];

    String username = '';
    String password = '';
    String host = '';
    int port = 1080;

    if (mainPart.contains('@')) {
      final atParts = mainPart.split('@');
      final userinfo = atParts[0];
      final hostPortStr = atParts[1];

      final hostPort = _parseHostPort(hostPortStr);
      host = hostPort.host;
      port = hostPort.port;

      String decodedUserinfo = userinfo;
      if (!userinfo.contains(':')) {
        try {
          decodedUserinfo = utf8.decode(base64.decode(_normalizeBase64(userinfo)));
        } catch (_) {}
      }

      final colonIdx = decodedUserinfo.indexOf(':');
      if (colonIdx != -1) {
        username = Uri.decodeComponent(decodedUserinfo.substring(0, colonIdx));
        password = Uri.decodeComponent(decodedUserinfo.substring(colonIdx + 1));
      } else {
        username = Uri.decodeComponent(decodedUserinfo);
      }
    } else {
      final hostPort = _parseHostPort(mainPart);
      host = hostPort.host;
      port = hostPort.port;
    }

    return ParsedProxyNode(
      protocol: 'socks',
      address: host,
      port: port,
      idOrPassword: username,
      encryption: password,
      remarks: remarks.isNotEmpty ? remarks : 'SOCKS Node',
    );
  }

  /// Parse http:// or https:// link
  static ParsedProxyNode _parseHttp(String link) {
    final isHttps = link.startsWith('https://');
    final prefixLen = isHttps ? 8 : 7;
    final uriStr = link.substring(prefixLen);
    final fragmentParts = uriStr.split('#');
    final remarks = fragmentParts.length > 1 ? Uri.decodeComponent(fragmentParts[1]) : (isHttps ? 'HTTPS Node' : 'HTTP Node');
    final beforeFragment = fragmentParts[0];

    final queryParts = beforeFragment.split('?');
    final queryString = queryParts.length > 1 ? queryParts[1] : '';
    final mainPart = queryParts[0];

    String username = '';
    String password = '';
    String host = '';
    int port = isHttps ? 443 : 80;

    if (mainPart.contains('@')) {
      final atParts = mainPart.split('@');
      final userinfo = atParts[0];
      final hostPortStr = atParts[1];

      final hostPort = _parseHostPort(hostPortStr);
      host = hostPort.host;
      port = hostPort.port;

      String decodedUserinfo = userinfo;
      if (!userinfo.contains(':')) {
        try {
          decodedUserinfo = utf8.decode(base64.decode(_normalizeBase64(userinfo)));
        } catch (_) {}
      }

      final colonIdx = decodedUserinfo.indexOf(':');
      if (colonIdx != -1) {
        username = Uri.decodeComponent(decodedUserinfo.substring(0, colonIdx));
        password = Uri.decodeComponent(decodedUserinfo.substring(colonIdx + 1));
      } else {
        username = Uri.decodeComponent(decodedUserinfo);
      }
    } else {
      final hostPort = _parseHostPort(mainPart);
      host = hostPort.host;
      port = hostPort.port;
    }

    final queryParams = _parseQueryString(queryString);
    final sni = queryParams['sni'] ?? queryParams['peer'] ?? host;

    return ParsedProxyNode(
      protocol: 'http',
      address: host,
      port: port,
      idOrPassword: username,
      encryption: password,
      security: isHttps ? 'tls' : 'none',
      sni: isHttps ? sni : null,
      remarks: remarks.isNotEmpty ? remarks : (isHttps ? 'HTTPS Node' : 'HTTP Node'),
    );
  }

  /// Generate full multi-hop Xray profile JSON structure
  static Map<String, dynamic> generateChainProfile({
    required List<String> nodeShareLinks,
    int socksPort = 10808,
    int httpPort = 10809,
  }) {
    if (nodeShareLinks.length < 2) {
      throw const FormatException('At least 2 nodes (Entry and Exit) are required for chaining.');
    }

    final parsedNodes = <ParsedProxyNode>[];
    for (int i = 0; i < nodeShareLinks.length; i++) {
      try {
        parsedNodes.add(parseLink(nodeShareLinks[i]));
      } catch (e) {
        throw FormatException('Failed to parse Hop $i: $e');
      }
    }

    final outbounds = <Map<String, dynamic>>[];

    for (int i = 0; i < parsedNodes.length; i++) {
      final tag = 'hop$i';
      final dialerProxyTag = i > 0 ? 'hop${i - 1}' : null;
      outbounds.add(parsedNodes[i].toXrayOutbound(
        tag: tag,
        dialerProxyTag: dialerProxyTag,
      ));
    }

    // Direct & Block outbounds
    outbounds.add({'tag': 'direct', 'protocol': 'freedom', 'settings': {}});
    outbounds.add({'tag': 'block', 'protocol': 'blackhole', 'settings': {}});

    final finalHopTag = 'hop${parsedNodes.length - 1}';

    // Summary remarks
    final entryProtocol = parsedNodes.first.protocol.toUpperCase();
    final exitProtocol = parsedNodes.last.protocol.toUpperCase();
    final remarks = 'Chained: $entryProtocol (Entry) → $exitProtocol (Exit)';

    final profile = <String, dynamic>{
      'remarks': remarks,
      'log': {'loglevel': 'warning'},
      'inbounds': [
        {
          'tag': 'socks-in',
          'port': socksPort,
          'listen': '127.0.0.1',
          'protocol': 'socks',
          'settings': {
            'udp': true,
            'auth': 'noauth',
          },
        },
        {
          'tag': 'http-in',
          'port': httpPort,
          'listen': '127.0.0.1',
          'protocol': 'http',
          'settings': {},
        },
      ],
      'outbounds': outbounds,
      'routing': {
        'rules': [
          {
            'type': 'field',
            'outboundTag': finalHopTag,
            'port': '0-65535',
          },
        ],
      },
    };

    return profile;
  }

  // --- Internal Utilities ---

  static String _normalizeBase64(String input) {
    var normalized = input.replaceAll('-', '+').replaceAll('_', '/');
    while (normalized.length % 4 != 0) {
      normalized += '=';
    }
    return normalized;
  }

  static _HostPort _parseHostPort(String input) {
    final colonIndex = input.lastIndexOf(':');
    if (colonIndex == -1) {
      throw FormatException('Invalid host:port string: $input');
    }
    final host = input.substring(0, colonIndex);
    final portStr = input.substring(colonIndex + 1);
    final port = int.tryParse(portStr);
    if (port == null || port <= 0 || port > 65535) {
      throw FormatException('Invalid port in host:port string: $portStr');
    }
    return _HostPort(host, port);
  }

  static Map<String, String> _parseQueryString(String query) {
    final params = <String, String>{};
    if (query.isEmpty) return params;
    final pairs = query.split('&');
    for (final pair in pairs) {
      if (pair.isEmpty) continue;
      final kv = pair.split('=');
      final key = Uri.decodeQueryComponent(kv[0]);
      final val = kv.length > 1 ? Uri.decodeQueryComponent(kv[1]) : '';
      params[key] = val;
    }
    return params;
  }
}

class _HostPort {
  final String host;
  final int port;
  _HostPort(this.host, this.port);
}
