import 'dart:async';

import 'package:drift/drift.dart';
import 'package:flutter/foundation.dart';

import '../../core/services/connectivity_service.dart';
import '../../models/database.dart';
import 'data/top_domains.dart';

/// State for a domain in the checker
class DomainCheckState {
  final String domain;
  final bool isDefault;
  final CheckStatus status;
  final ConnectivityResult? result;

  DomainCheckState({
    required this.domain,
    required this.isDefault,
    this.status = CheckStatus.idle,
    this.result,
  });

  DomainCheckState copyWith({
    CheckStatus? status,
    ConnectivityResult? result,
  }) {
    return DomainCheckState(
      domain: domain,
      isDefault: isDefault,
      status: status ?? this.status,
      result: result ?? this.result,
    );
  }
}

enum CheckStatus { idle, checking, success, failure }

class DomainCheckerController extends ChangeNotifier {
  final AppDatabase _db = AppDatabase.instance;

  List<DomainCheckState> _domains = [];
  List<Preset> _presets = [];
  Preset? _activePreset;
  bool _isEditMode = false;

  bool _isLoading = false;
  bool _isChecking = false;
  int _checkedCount = 0;
  int _successCount = 0;
  int _failureCount = 0;
  
  // Throttle UI updates for better performance
  Timer? _updateTimer;
  bool _hasPendingUpdate = false;
  static const _updateInterval = Duration(milliseconds: 100);

  List<DomainCheckState> get domains => _domains;
  List<Preset> get presets => _presets;
  Preset? get activePreset => _activePreset;
  bool get isEditMode => _isEditMode;

  bool get isLoading => _isLoading;
  bool get isChecking => _isChecking;
  int get checkedCount => _checkedCount;
  int get successCount => _successCount;
  int get failureCount => _failureCount;
  int get totalCount => _domains.length;
  double get progress => totalCount > 0 ? _checkedCount / totalCount : 0;
  
  /// Throttled notify - batches updates to avoid excessive UI rebuilds
  void _throttledNotify() {
    _hasPendingUpdate = true;
    _updateTimer ??= Timer(_updateInterval, () {
      _updateTimer = null;
      if (_hasPendingUpdate) {
        _hasPendingUpdate = false;
        notifyListeners();
      }
    });
  }
  
  /// Force immediate notification (for important state changes)
  void _immediateNotify() {
    _updateTimer?.cancel();
    _updateTimer = null;
    _hasPendingUpdate = false;
    notifyListeners();
  }
  
  @override
  void dispose() {
    _updateTimer?.cancel();
    super.dispose();
  }

  DomainCheckerController() {
    _loadDomains();
  }

  Future<void> _loadDomains() async {
    _isLoading = true;
    notifyListeners();

    try {
      // Sync default domains - add any missing ones from the hardcoded list
      await _syncDefaultDomains();
      
      // Load all presets
      _presets = await _db.getAllPresets();
      
      // Select the active preset
      if (_activePreset == null || !_presets.any((p) => p.id == _activePreset!.id)) {
        _activePreset = _presets.firstWhere((p) => p.isSystem, orElse: () => _presets.first);
      } else {
        _activePreset = _presets.firstWhere((p) => p.id == _activePreset!.id);
      }
      
      // Load domains for active preset
      final dbDomains = await _db.getDomainsByPreset(_activePreset!.id);
      _domains = dbDomains.map((d) => DomainCheckState(
        domain: d.url,
        isDefault: d.isDefault,
      )).toList();
    } catch (e) {
      debugPrint('Error loading domains: $e');
      // Fallback to hardcoded list
      _domains = topDomains.map((d) => DomainCheckState(
        domain: d,
        isDefault: true,
      )).toList();
    }

    _isLoading = false;
    notifyListeners();
  }

  Future<void> _syncDefaultDomains() async {
    final defaultPreset = await _db.getDefaultPreset();
    final existingDomains = await _db.getDomainsByPreset(defaultPreset.id);
    final existingUrls = existingDomains.map((d) => d.url).toSet();
    
    // Find domains that are in topDomains but not in the database for this preset
    final newDomains = topDomains
        .where((domain) => !existingUrls.contains(domain))
        .map((domain) => DomainEntriesCompanion.insert(
              url: domain,
              isDefault: const Value(true),
              presetId: Value(defaultPreset.id),
            ))
        .toList();
    
    if (newDomains.isNotEmpty) {
      await _db.insertDomains(newDomains);
      debugPrint('Added ${newDomains.length} new default domains');
    }
  }

  Future<void> selectPreset(Preset preset) async {
    if (_isChecking) {
      stopChecking();
    }
    _activePreset = preset;
    _isEditMode = false;
    resetResults();
    
    _isLoading = true;
    notifyListeners();
    try {
      final dbDomains = await _db.getDomainsByPreset(preset.id);
      _domains = dbDomains.map((d) => DomainCheckState(
        domain: d.url,
        isDefault: d.isDefault,
      )).toList();
    } catch (e) {
      debugPrint('Error loading preset domains: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> createPreset(String name) async {
    if (name.trim().isEmpty) return;
    try {
      final id = await _db.insertPreset(PresetsCompanion.insert(
        name: name.trim(),
        isSystem: const Value(false),
      ));
      
      _presets = await _db.getAllPresets();
      final newPreset = _presets.firstWhere((p) => p.id == id);
      await selectPreset(newPreset);
    } catch (e) {
      debugPrint('Error creating preset: $e');
    }
  }

  Future<void> editPresetName(int id, String newName) async {
    if (newName.trim().isEmpty) return;
    try {
      await _db.updatePresetName(id, newName.trim());
      _presets = await _db.getAllPresets();
      if (_activePreset?.id == id) {
        _activePreset = _presets.firstWhere((p) => p.id == id);
      }
      notifyListeners();
    } catch (e) {
      debugPrint('Error renaming preset: $e');
    }
  }

  Future<void> deletePreset(int id) async {
    try {
      final presetToDelete = _presets.firstWhere((p) => p.id == id);
      if (presetToDelete.isSystem) return;

      await _db.deletePreset(id);
      
      if (_activePreset?.id == id) {
        final defaultPreset = await _db.getDefaultPreset();
        await selectPreset(defaultPreset);
      } else {
        _presets = await _db.getAllPresets();
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error deleting preset: $e');
    }
  }

  void setEditMode(bool value) {
    _isEditMode = value;
    notifyListeners();
  }

  Future<void> addDomain(String url) async {
    if (_activePreset == null) return;
    
    // Normalize URL
    String normalizedUrl = url.trim().toLowerCase();
    if (normalizedUrl.startsWith('http://')) {
      normalizedUrl = normalizedUrl.substring(7);
    } else if (normalizedUrl.startsWith('https://')) {
      normalizedUrl = normalizedUrl.substring(8);
    }
    if (normalizedUrl.endsWith('/')) {
      normalizedUrl = normalizedUrl.substring(0, normalizedUrl.length - 1);
    }

    // Check if already exists in active preset
    final exists = _domains.any((d) => d.domain == normalizedUrl);
    if (exists) return;

    // Add to database
    await _db.insertDomain(DomainEntriesCompanion.insert(
      url: normalizedUrl,
      isDefault: Value(_activePreset!.isSystem),
      presetId: Value(_activePreset!.id),
    ));

    // Refresh active preset domains list
    await selectPreset(_activePreset!);
  }

  Future<void> removeDomain(String domain) async {
    if (_activePreset == null) return;
    
    try {
      // Find and remove from database
      final dbDomains = await _db.getDomainsByPreset(_activePreset!.id);
      final entry = dbDomains.firstWhere(
        (d) => d.url == domain,
        orElse: () => throw Exception('Domain not found'),
      );
      
      await _db.deleteDomain(entry.id);
      _domains.removeWhere((d) => d.domain == domain);
      notifyListeners();
    } catch (e) {
      debugPrint('Error removing domain: $e');
    }
  }

  Future<void> deleteAllDomainsInActivePreset() async {
    if (_activePreset == null) return;
    try {
      await _db.deleteDomainsByPreset(_activePreset!.id);
      _domains.clear();
      notifyListeners();
    } catch (e) {
      debugPrint('Error deleting all domains in preset: $e');
    }
  }

  Future<void> resetDatabase() async {
    _isLoading = true;
    _isEditMode = false;
    _activePreset = null;
    notifyListeners();

    try {
      await _db.resetDatabase();
      await _loadDomains();
    } catch (e) {
      debugPrint('Error resetting database: $e');
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> checkAll() async {
    if (_isChecking) return;

    _isChecking = true;
    _checkedCount = 0;
    _successCount = 0;
    _failureCount = 0;

    // Reset all statuses to checking
    _domains = _domains.map((d) => d.copyWith(
      status: CheckStatus.checking,
      result: null,
    )).toList();
    _immediateNotify(); // Show spinners immediately

    final targets = _domains.map((d) => d.domain).toList();

    await for (final result in ConnectivityService.checkMultiple(targets)) {
      // Check if stop was requested
      if (!_isChecking) {
        // Mark remaining domains as idle
        _domains = _domains.map((d) {
          if (d.status == CheckStatus.checking) {
            return d.copyWith(status: CheckStatus.idle);
          }
          return d;
        }).toList();
        _immediateNotify();
        return;
      }

      final index = _domains.indexWhere((d) => d.domain == result.target);
      if (index != -1) {
        _domains[index] = _domains[index].copyWith(
          status: result.success ? CheckStatus.success : CheckStatus.failure,
          result: result,
        );
        
        _checkedCount++;
        if (result.success) {
          _successCount++;
        } else {
          _failureCount++;
        }

        _throttledNotify(); // Batch UI updates for results
      }
    }

    _isChecking = false;
    _immediateNotify(); // Ensure final state is shown
  }

  Future<void> checkSingle(String domain) async {
    final index = _domains.indexWhere((d) => d.domain == domain);
    if (index == -1) return;

    _domains[index] = _domains[index].copyWith(status: CheckStatus.checking);
    notifyListeners();

    final result = await ConnectivityService.checkSingle(domain);
    
    _domains[index] = _domains[index].copyWith(
      status: result.success ? CheckStatus.success : CheckStatus.failure,
      result: result,
    );
    notifyListeners();
  }

  void stopChecking() {
    _isChecking = false;
    _immediateNotify();
  }

  void resetResults() {
    _domains = _domains.map((d) => DomainCheckState(
      domain: d.domain,
      isDefault: d.isDefault,
    )).toList();
    _checkedCount = 0;
    _successCount = 0;
    _failureCount = 0;
    notifyListeners();
  }

  Future<void> refresh() async {
    await _loadDomains();
  }
}

