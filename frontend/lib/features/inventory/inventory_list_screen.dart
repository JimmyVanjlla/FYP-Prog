import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/theme.dart';
import '../../models/ingredient.dart';

/// Module 3 — FR3.1/FR3.3. Every role can view stock levels; only
/// Inventory Staff and the Restaurant Manager can add ingredients or record
/// adjustments (server-enforced; this screen mirrors that client-side).
class InventoryListScreen extends StatefulWidget {
  const InventoryListScreen({super.key});

  @override
  State<InventoryListScreen> createState() => _InventoryListScreenState();
}

class _InventoryListScreenState extends State<InventoryListScreen> {
  late Future<List<Ingredient>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Ingredient>> _load() async {
    final api = context.read<AuthState>().api;
    final raw = await api.listIngredients();
    return raw
        .map((e) => Ingredient.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  bool get _canManage {
    final role = context.read<AuthState>().role;
    return role == Roles.inventoryStaff || role == Roles.manager;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Ingredient>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          final message = snapshot.error is ApiException
              ? (snapshot.error as ApiException).message
              : 'Failed to load inventory.';
          return Center(child: Text(message));
        }
        final ingredients = snapshot.data ?? [];
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: ingredients.length + (_canManage ? 1 : 0),
            separatorBuilder: (_, _) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              if (_canManage && index == ingredients.length) {
                return _AddIngredientRow(onAdded: _refresh);
              }
              return _IngredientTile(
                ingredient: ingredients[index],
                onChanged: _refresh,
              );
            },
          ),
        );
      },
    );
  }
}

class _IngredientTile extends StatelessWidget {
  final Ingredient ingredient;
  final Future<void> Function() onChanged;

  const _IngredientTile({required this.ingredient, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(ingredient.name),
        subtitle: Text('${ingredient.currentStock} ${ingredient.unit} on hand'),
        trailing: SeverityChip(
          label: ingredient.isLowStock ? 'Low stock' : 'OK',
          color: ingredient.isLowStock ? Severity.critical : Severity.ok,
        ),
        onTap: () => _showAdjustDialog(context),
      ),
    );
  }

  Future<void> _showAdjustDialog(BuildContext context) async {
    final qtyController = TextEditingController();
    String reason = 'miscount';
    final formKey = GlobalKey<FormState>();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text('Adjust ${ingredient.name}'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: qtyController,
                  keyboardType: const TextInputType.numberWithOptions(
                    signed: true,
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Adjustment (+/-)',
                    helperText:
                        'e.g. -2.5 for spoilage, +5 to correct a miscount',
                  ),
                  // FR3.6 — validated inline, at the point of entry.
                  validator: (v) {
                    if (v == null || v.trim().isEmpty) {
                      return 'Enter a quantity.';
                    }
                    final parsed = num.tryParse(v.trim());
                    if (parsed == null) return 'Must be a number.';
                    if (parsed == 0) return 'Cannot be zero.';
                    return null;
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: reason,
                  decoration: const InputDecoration(labelText: 'Reason'),
                  items: const ['spillage', 'spoilage', 'miscount']
                      .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                      .toList(),
                  onChanged: (v) => setState(() => reason = v ?? reason),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) {
                  Navigator.of(context).pop(true);
                }
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );

    if (confirmed != true || !context.mounted) return;
    try {
      final api = context.read<AuthState>().api;
      await api.recordStockAdjustment(
        ingredientId: ingredient.ingredientId,
        adjustedQuantity: qtyController.text.trim(),
        reasonCategory: reason,
      );
      await onChanged();
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _AddIngredientRow extends StatelessWidget {
  final Future<void> Function() onAdded;

  const _AddIngredientRow({required this.onAdded});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: () => _showAddDialog(context),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          border: Border.all(color: Theme.of(context).colorScheme.outline),
          borderRadius: BorderRadius.circular(8),
        ),
        alignment: Alignment.center,
        child: const Text('+ Add ingredient'),
      ),
    );
  }

  Future<void> _showAddDialog(BuildContext context) async {
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
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required.' : null,
              ),
              TextFormField(
                controller: unitController,
                decoration: const InputDecoration(
                  labelText: 'Unit (e.g. kg, litre)',
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required.' : null,
              ),
              TextFormField(
                controller: stockController,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(labelText: 'Current stock'),
                validator: (v) {
                  final parsed = num.tryParse(v?.trim() ?? '');
                  if (parsed == null || parsed < 0) {
                    return 'Must be a number ≥ 0.';
                  }
                  return null;
                },
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) {
                Navigator.of(context).pop(true);
              }
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );

    if (confirmed != true || !context.mounted) return;
    try {
      final api = context.read<AuthState>().api;
      await api.createIngredient(
        name: nameController.text.trim(),
        unit: unitController.text.trim(),
        currentStock: stockController.text.trim(),
      );
      await onAdded();
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
