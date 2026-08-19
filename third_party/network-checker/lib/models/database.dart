import 'package:drift/drift.dart';
import 'package:drift_flutter/drift_flutter.dart';

part 'database.g.dart';

/// Table for storing domain list entries
class DomainEntries extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get url => text().withLength(min: 1, max: 500)();
  BoolColumn get isDefault => boolean().withDefault(const Constant(false))();
  IntColumn get presetId => integer().nullable().references(Presets, #id, onDelete: KeyAction.cascade)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}

/// Table for storing domain presets
class Presets extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get name => text().withLength(min: 1, max: 100)();
  BoolColumn get isSystem => boolean().withDefault(const Constant(false))();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}

@DriftDatabase(tables: [DomainEntries, Presets])
class AppDatabase extends _$AppDatabase {
  AppDatabase._() : super(_openConnection());

  static AppDatabase? _instance;

  static AppDatabase get instance {
    _instance ??= AppDatabase._();
    return _instance!;
  }

  @override
  int get schemaVersion => 3;

  @override
  MigrationStrategy get migration {
    return MigrationStrategy(
      onCreate: (Migrator m) async {
        await m.createAll();
      },
      onUpgrade: (Migrator m, int from, int to) async {
        if (from < 2) {
          // Drop the old history tables if they exist
          await customStatement('DROP TABLE IF EXISTS check_results');
          await customStatement('DROP TABLE IF EXISTS check_sessions');
        }
        if (from < 3) {
          await m.createTable(presets);
          await m.addColumn(domainEntries, domainEntries.presetId);
        }
      },
      beforeOpen: (details) async {
        // Seed default preset and link unassociated domain entries to default preset
        final defaultPreset = await _getDefaultPresetInternal();
        await (update(domainEntries)..where((d) => d.presetId.isNull())).write(
          DomainEntriesCompanion(presetId: Value(defaultPreset.id)),
        );
      },
    );
  }

  static QueryExecutor _openConnection() {
    return driftDatabase(name: 'rdnbenet_db');
  }

  Future<Preset> _getDefaultPresetInternal() async {
    final defaultPreset = await (select(presets)..where((p) => p.isSystem.equals(true) & p.name.equals('Default'))).getSingleOrNull();
    if (defaultPreset != null) {
      return defaultPreset;
    }
    final id = await into(presets).insert(PresetsCompanion.insert(
      name: 'Default',
      isSystem: const Value(true),
    ));
    return (select(presets)..where((p) => p.id.equals(id))).getSingle();
  }

  // Domain Entry Operations
  Future<List<DomainEntry>> getAllDomains() => select(domainEntries).get();

  Future<List<DomainEntry>> getDefaultDomains() =>
      (select(domainEntries)..where((d) => d.isDefault.equals(true))).get();

  Future<List<DomainEntry>> getCustomDomains() =>
      (select(domainEntries)..where((d) => d.isDefault.equals(false))).get();

  Future<int> insertDomain(DomainEntriesCompanion entry) =>
      into(domainEntries).insert(entry);

  Future<void> insertDomains(List<DomainEntriesCompanion> entries) async {
    await batch((batch) {
      batch.insertAll(domainEntries, entries);
    });
  }

  Future<int> deleteDomain(int id) =>
      (delete(domainEntries)..where((d) => d.id.equals(id))).go();

  Future<int> deleteCustomDomains() =>
      (delete(domainEntries)..where((d) => d.isDefault.equals(false))).go();

  Future<bool> domainExists(String url) async {
    final query = select(domainEntries)..where((d) => d.url.equals(url));
    final result = await query.getSingleOrNull();
    return result != null;
  }

  // Preset Operations
  Future<List<Preset>> getAllPresets() => select(presets).get();

  Future<Preset> getDefaultPreset() => _getDefaultPresetInternal();

  Future<int> insertPreset(PresetsCompanion entry) => into(presets).insert(entry);

  Future<int> deletePreset(int id) => (delete(presets)..where((p) => p.id.equals(id))).go();

  Future<bool> updatePresetName(int id, String name) async {
    final count = await (update(presets)..where((p) => p.id.equals(id))).write(
      PresetsCompanion(name: Value(name)),
    );
    return count > 0;
  }

  Future<List<DomainEntry>> getDomainsByPreset(int presetId) =>
      (select(domainEntries)..where((d) => d.presetId.equals(presetId))).get();

  Future<int> deleteDomainsByPreset(int presetId) =>
      (delete(domainEntries)..where((d) => d.presetId.equals(presetId))).go();

  Future<void> resetDatabase() async {
    await transaction(() async {
      await delete(domainEntries).go();
      await (delete(presets)..where((p) => p.isSystem.equals(false))).go();
    });
  }
}
