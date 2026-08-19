import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:rdnbenet/features/chain/chain_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ChainController Tests', () {
    late ChainController controller;

    setUp(() {
      controller = ChainController();
    });

    test('initial state has two empty hop links and default ports', () {
      expect(controller.hopLinks.length, equals(2));
      expect(controller.hopLinks[0], isEmpty);
      expect(controller.hopLinks[1], isEmpty);
      expect(controller.socksPort, equals(10808));
      expect(controller.httpPort, equals(10809));
      expect(controller.generatedJson, isNull);
      expect(controller.errorMessage, isNull);
    });

    test('swaps entry and exit hop links correctly', () {
      controller.setHopLink(0, 'vless://entry-link');
      controller.setHopLink(1, 'vless://exit-link');

      controller.swapHops(0, 1);

      expect(controller.hopLinks[0], equals('vless://exit-link'));
      expect(controller.hopLinks[1], equals('vless://entry-link'));
    });

    test('adds and removes intermediate hops', () {
      expect(controller.hopLinks.length, equals(2));

      controller.addHopLink();
      expect(controller.hopLinks.length, equals(3));

      controller.setHopLink(1, 'vless://middle-link');
      expect(controller.hopLinks[1], equals('vless://middle-link'));

      controller.removeHopLink(1);
      expect(controller.hopLinks.length, equals(2));
    });

    test('sets error message when generating with empty links', () async {
      await controller.generateChain();

      expect(controller.generatedJson, isNull);
      expect(controller.errorMessage, contains('Please provide at least 2 valid proxy links'));
    });

    test('generates valid Xray JSON profile with valid VLESS links', () async {
      controller.setHopLink(
        0,
        'vless://00000000-0000-0000-0000-000000000001@entry.example.com:443?type=ws&security=tls&path=%2Fentry-path#EntryNode',
      );
      controller.setHopLink(
        1,
        'vless://00000000-0000-0000-0000-000000000002@exit.example.com:443?type=ws&security=tls&path=%2Fexit-path#ExitNode',
      );

      await controller.generateChain();

      expect(controller.errorMessage, isNull);
      expect(controller.generatedJson, isNotNull);

      final profile = json.decode(controller.generatedJson!) as Map<String, dynamic>;

      final outbounds = profile['outbounds'] as List;
      expect(outbounds[0]['tag'], equals('hop0'));
      expect(outbounds[1]['tag'], equals('hop1'));
      expect(outbounds[1]['streamSettings']['sockopt']['dialerProxy'], equals('hop0'));
    });
  });
}
