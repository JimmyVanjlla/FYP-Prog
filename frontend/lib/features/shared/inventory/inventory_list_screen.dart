import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';
import 'ingredient_detail_screen.dart';

/// Module 3 — FR3.1/FR3.3. Every role can view stock levels; only Inventory
/// Staff and the Restaurant Manager can add ingredients or record
/// adjustments (server-enforced; this screen mirrors that client-side).
/// Each row shows on-hand beside the threshold it's measured against (Ch4
/// §4.4.1: "on-hand quantity next to the low-stock threshold"), and opens
/// the ingredient's detail.
class InventoryListScreen extends StatefulWidget {
  const InventoryListScreen({super.key});

  @override
  State<InventoryListScreen> createState() => _InventoryListScreenState();
}

class _InventoryListScreenState extends State<InventoryListScreen> {
  int _version = 0;

  bool get _canManage {
    final role = context.read<AuthState>().role;
    return role == Roles.inventoryStaff || role == Roles.manager;
  }

  Future<({List<Json> ingredients, double defaultThreshold})> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/inventory/ingredients', query: {'limit': 500}),
      api.getJson('/config'),
    ]);
    return (
      ingredients: asJsonList(results[0]),
      defaultThreshold: asDouble(asJson(results[1])['default_low_stock_threshold']),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AsyncView<({List<Json> ingredients, double defaultThreshold})>(
      key: ValueKey(_version),
      load: _load,
      builder: (context, data, reload) {
        final groups = groupByPriority(data.ingredients, data.defaultThreshold);
        Widget tile(Json ingredient) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _IngredientTile(
            ingredient: ingredient,
            defaultThreshold: data.defaultThreshold,
            onTap: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => IngredientDetailScreen(ingredientId: ingredient['ingredient_id'] as int),
                ),
              );
              if (mounted) setState(() => _version++);
            },
          ),
        );
        return RefreshableList(
          onRefresh: reload,
          empty: _canManage
              ? null
              : const EmptyState(icon: Icons.inventory_2_outlined, message: 'No ingredients tracked yet.'),
          children: [
            if (data.ingredients.isNotEmpty) ...[
              Row(
                children: [
                  Expanded(
                    child: StatTile(
                      icon: groups.low.isEmpty ? Icons.check_circle_rounded : Icons.error_rounded,
                      value: '${groups.low.length}',
                      label: 'Low stock',
                      color: groups.low.isEmpty ? Severity.ok : Severity.critical,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatTile(
                      icon: Icons.check_circle_rounded,
                      value: '${groups.ok.length}',
                      label: 'Well stocked',
                      color: Severity.ok,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatTile(
                      icon: Icons.inventory_2_rounded,
                      value: '${data.ingredients.length}',
                      label: 'Ingredients',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
            ],
            // Low stock first, most urgent at the top, then everything else.
            if (groups.low.isNotEmpty) ...[
              SectionHeader(
                icon: Icons.error_rounded,
                label: 'Low stock: restock these',
                trailing: '${groups.low.length}',
                color: Severity.critical,
              ),
              for (final ingredient in groups.low) tile(ingredient),
              const SizedBox(height: 8),
            ],
            if (groups.ok.isNotEmpty) ...[
              SectionHeader(
                icon: Icons.check_circle_rounded,
                label: 'Well stocked',
                trailing: '${groups.ok.length}',
                color: Severity.ok,
              ),
              for (final ingredient in groups.ok) tile(ingredient),
            ],
            if (_canManage) AddRow(label: 'Add ingredient', onTap: () => _showAddDialog(context, reload)),
          ],
        );
      },
    );
  }

  Future<void> _showAddDialog(BuildContext context, Future<void> Function() reload) async {
    final nameController = TextEditingController();
    final unitController = TextEditingController(text: 'kg');
    final stockController = TextEditingController(text: '0');
    final formKey = GlobalKey<FormState>();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('New ingredient'),
        content: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: nameController,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: unitController,
                decoration: const InputDecoration(labelText: 'Unit (e.g. kg, litre)'),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: stockController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Current stock'),
                validator: (v) {
                  final parsed = num.tryParse(v?.trim() ?? '');
                  if (parsed == null || parsed < 0) return 'Must be a number ≥ 0.';
                  return null;
                },
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) Navigator.of(context).pop(true);
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );

    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.createIngredient(
        name: nameController.text.trim(),
        unit: unitController.text.trim(),
        currentStock: stockController.text.trim(),
      ),
      success: 'Ingredient added.',
    );
    if (ok) await reload();
  }
}

/// Splits ingredients into low stock and the rest, each in a sensible order.
/// Low stock is sorted by how far below its threshold it is (the emptiest,
/// relative to what it should hold, first), so the first row is always the
/// most urgent one; the rest are alphabetical.
({List<Json> low, List<Json> ok}) groupByPriority(List<Json> ingredients, double defaultThreshold) {
  double fill(Json i) {
    final own = i['low_stock_threshold'];
    final threshold = own == null ? defaultThreshold : asDouble(own);
    return threshold <= 0 ? 0 : asDouble(i['current_stock']) / threshold;
  }

  String name(Json i) => (i['name'] as String).toLowerCase();
  final low = [for (final i in ingredients) if (i['is_low_stock'] == true) i]
    ..sort((a, b) {
      final byFill = fill(a).compareTo(fill(b));
      return byFill != 0 ? byFill : name(a).compareTo(name(b));
    });
  final ok = [for (final i in ingredients) if (i['is_low_stock'] != true) i]..sort((a, b) => name(a).compareTo(name(b)));
  return (low: low, ok: ok);
}

class _IngredientTile extends StatelessWidget {
  final Json ingredient;
  final double defaultThreshold;
  final VoidCallback onTap;

  const _IngredientTile({required this.ingredient, required this.defaultThreshold, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final low = ingredient['is_low_stock'] == true;
    final own = ingredient['low_stock_threshold'];
    final threshold = own == null ? defaultThreshold : asDouble(own);
    return Card(
      child: ListTile(
        onTap: onTap,
        leading: IconBadge(icon: Icons.inventory_2_rounded, color: low ? Severity.critical : null),
        title: Text(ingredient['name'] as String),
        subtitle: Text(
          '${trimNum(ingredient['current_stock'])} ${ingredient['unit']} on hand'
          '  ·  alert below ${trimNum(threshold)}${own == null ? ' (default)' : ''}',
        ),
        trailing: SeverityChip(
          label: low ? 'Low stock' : 'OK',
          color: low ? Severity.critical : Severity.ok,
        ),
      ),
    );
  }
}
