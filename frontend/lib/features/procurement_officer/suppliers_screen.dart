import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/dialogs.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// FR9.1 / UC-PS-04 — the supplier directory: contact details and the price
/// each supplier charges per ingredient. A supplier can be deactivated
/// (kept for history, excluded from new orders).
class SuppliersScreen extends StatefulWidget {
  const SuppliersScreen({super.key});

  @override
  State<SuppliersScreen> createState() => _SuppliersScreenState();
}

class _SuppliersScreenState extends State<SuppliersScreen> {
  int _version = 0;

  Future<void> _addSupplier(BuildContext context, Future<void> Function() reload) async {
    final name = TextEditingController();
    final contact = TextEditingController();
    final formKey = GlobalKey<FormState>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('New supplier'),
        content: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Supplier name'),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: contact,
                decoration: const InputDecoration(labelText: 'Contact (phone / email)'),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) Navigator.pop(context, true);
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
      () => api.postJson('/procurement/suppliers', {
        'name': name.text.trim(),
        'contact_info': contact.text.trim(),
      }),
      success: 'Supplier added.',
    );
    if (ok) await reload();
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<List<Json>>(
      key: ValueKey(_version),
      load: () async => asJsonList(await api.getJson('/procurement/suppliers', query: {'limit': 500})),
      builder: (context, suppliers, reload) => RefreshableList(
        onRefresh: reload,
        children: [
          for (final s in suppliers) ...[
            Card(
              child: ListTile(
                onTap: () async {
                  await Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => SupplierDetailScreen(supplier: s)),
                  );
                  if (mounted) setState(() => _version++);
                },
                leading: IconBadge(
                  icon: Icons.storefront_rounded,
                  color: s['is_active'] == true ? null : Severity.critical,
                ),
                title: Text(s['name'] as String),
                subtitle: Text(s['contact_info'] as String),
                trailing: s['is_active'] == true
                    ? const Icon(Icons.chevron_right_rounded)
                    : const SeverityChip(label: 'Inactive', color: Severity.critical),
              ),
            ),
            const SizedBox(height: 10),
          ],
          AddRow(label: 'Add supplier', onTap: () => _addSupplier(context, reload)),
        ],
      ),
    );
  }
}

/// One supplier's price list, with the ability to set a price per ingredient
/// and to deactivate the supplier.
class SupplierDetailScreen extends StatefulWidget {
  final Json supplier;

  const SupplierDetailScreen({super.key, required this.supplier});

  @override
  State<SupplierDetailScreen> createState() => _SupplierDetailScreenState();
}

class _SupplierDetailScreenState extends State<SupplierDetailScreen> {
  int _version = 0;
  late bool _active = widget.supplier['is_active'] == true;

  int get _id => widget.supplier['supplier_id'] as int;

  Future<void> _setPrice(BuildContext context, List<Json> ingredients, Future<void> Function() reload) async {
    if (ingredients.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('There are no ingredients yet. Add them in Inventory first.')),
      );
      return;
    }
    int ingredientId = ingredients.first['ingredient_id'] as int;
    final price = TextEditingController();
    final formKey = GlobalKey<FormState>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Set a price'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<int>(
                  initialValue: ingredientId,
                  decoration: const InputDecoration(labelText: 'Ingredient'),
                  items: [
                    for (final i in ingredients)
                      DropdownMenuItem(value: i['ingredient_id'] as int, child: Text('${i['name']} (per ${i['unit']})')),
                  ],
                  onChanged: (v) => setState(() => ingredientId = v ?? ingredientId),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: price,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Unit price', prefixText: 'RM '),
                  validator: (v) {
                    final n = double.tryParse(v?.trim() ?? '');
                    if (n == null) return 'Enter a number.';
                    if (n <= 0) return 'Must be greater than zero.';
                    return null;
                  },
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) Navigator.pop(context, true);
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/procurement/suppliers/pricing', {
        'supplier_id': _id,
        'ingredient_id': ingredientId,
        'unit_price': price.text.trim(),
      }),
      success: 'Price saved.',
    );
    if (ok) await reload();
  }

  Future<void> _deactivate(BuildContext context) async {
    final proceed = await confirmAction(
      context,
      title: 'Deactivate ${widget.supplier['name']}?',
      message: 'Past orders are kept, but this supplier is left out of new purchase orders.',
      confirmLabel: 'Deactivate',
    );
    if (!proceed || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/procurement/suppliers/$_id/deactivate', {}),
      success: 'Supplier deactivated.',
    );
    if (ok && mounted) setState(() => _active = false);
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return Scaffold(
      appBar: AppBar(title: Text(widget.supplier['name'] as String)),
      body: AsyncView<({List<Json> prices, List<Json> ingredients})>(
        key: ValueKey(_version),
        load: () async {
          final results = await Future.wait([
            api.getJson('/procurement/suppliers/pricing', query: {'supplier_id': _id, 'limit': 500}),
            api.getJson('/inventory/ingredients', query: {'limit': 500}),
          ]);
          return (prices: asJsonList(results[0]), ingredients: asJsonList(results[1]));
        },
        builder: (context, data, reload) {
          final names = {for (final i in data.ingredients) i['ingredient_id'] as int: i};
          return RefreshableList(
            onRefresh: reload,
            children: [
              Card(
                child: ListTile(
                  leading: const IconBadge(icon: Icons.call_rounded),
                  title: Text(widget.supplier['contact_info'] as String),
                  trailing: SeverityChip(
                    label: _active ? 'Active' : 'Inactive',
                    color: _active ? Severity.ok : Severity.critical,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              SectionHeader(icon: Icons.sell_rounded, label: 'Price list', trailing: '${data.prices.length}'),
              if (data.prices.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('No prices set yet. Add the ingredients this supplier provides.'),
                ),
              for (final p in data.prices)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Card(
                    child: ListTile(
                      dense: true,
                      title: Text(names[p['ingredient_id']]?['name'] as String? ?? 'Ingredient #${p['ingredient_id']}'),
                      trailing: Text(
                        '${money(p['unit_price'])} / ${names[p['ingredient_id']]?['unit'] ?? 'unit'}',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                ),
              AddRow(
                label: 'Set a price',
                onTap: () => _setPrice(context, data.ingredients, () async {
                  setState(() => _version++);
                }),
              ),
              if (_active) ...[
                const SizedBox(height: 24),
                OutlinedButton.icon(
                  onPressed: () => _deactivate(context),
                  icon: const Icon(Icons.block_rounded),
                  label: const Text('Deactivate supplier'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
