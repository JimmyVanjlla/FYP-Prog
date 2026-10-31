import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';

/// FR2.1 / FR2.2 — one menu item: its profit margin and availability, the
/// recipe it's built from, and (for the Restaurant Manager) editing,
/// deactivating and changing that recipe. Everyone else sees it read-only.
class MenuDetailScreen extends StatefulWidget {
  final int menuItemId;

  const MenuDetailScreen({super.key, required this.menuItemId});

  @override
  State<MenuDetailScreen> createState() => _MenuDetailScreenState();
}

class _MenuDetailScreenState extends State<MenuDetailScreen> {
  Future<({Json item, List<Json> ingredients})> _load() async {
    final api = context.read<AuthState>().api;
    final items = asJsonList(await api.getJson('/menu-items', query: {'include_inactive': true, 'limit': 500}));
    final ingredients = asJsonList(await api.getJson('/inventory/ingredients', query: {'limit': 500}));
    final item = items.firstWhere((i) => i['menu_item_id'] == widget.menuItemId);
    return (item: item, ingredients: ingredients);
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = context.read<AuthState>().role == Roles.manager;
    return Scaffold(
      appBar: AppBar(title: const Text('Menu item')),
      body: AsyncView<({Json item, List<Json> ingredients})>(
        load: _load,
        builder: (context, data, reload) {
          final item = data.item;
          final names = {for (final i in data.ingredients) i['ingredient_id'] as int: i};
          final links = asJsonList(item['recipe_links']);
          final active = item['is_active'] as bool;
          return RefreshableList(
            onRefresh: reload,
            children: [
              _SummaryCard(item: item),
              const SizedBox(height: 16),
              SectionHeader(icon: Icons.menu_book_rounded, label: 'Recipe', trailing: '${links.length} ingredients'),
              if (links.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('No ingredients linked yet, so profit margin and availability can not be worked out.'),
                ),
              for (final link in links)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Card(
                    child: ListTile(
                      leading: const IconBadge(icon: Icons.grain_rounded),
                      title: Text(names[link['ingredient_id']]?['name'] as String? ?? 'Ingredient #${link['ingredient_id']}'),
                      subtitle: Text(
                        '${trimNum(link['quantity_per_serving'])} ${names[link['ingredient_id']]?['unit'] ?? ''} per serving',
                      ),
                      trailing: canEdit
                          ? IconButton(
                              tooltip: 'Remove from recipe',
                              icon: const Icon(Icons.delete_outline_rounded),
                              onPressed: () => _removeLink(context, link, reload),
                            )
                          : null,
                    ),
                  ),
                ),
              if (canEdit) ...[
                AddRow(
                  label: 'Add ingredient',
                  onTap: () => _addLink(context, data.ingredients, links, reload),
                ),
                const SizedBox(height: 24),
                _EditForm(item: item, onSaved: reload),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  icon: Icon(active ? Icons.visibility_off_rounded : Icons.visibility_rounded),
                  label: Text(active ? 'Deactivate menu item' : 'Reactivate menu item'),
                  onPressed: () => _toggleActive(context, item, reload),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<void> _removeLink(BuildContext context, Json link, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.deleteJson('/menu-items/${widget.menuItemId}/recipe-links/${link['link_id']}'),
      success: 'Removed from recipe.',
    );
    if (ok) await reload();
  }

  Future<void> _addLink(
    BuildContext context,
    List<Json> ingredients,
    List<Json> existing,
    Future<void> Function() reload,
  ) async {
    final used = existing.map((l) => l['ingredient_id']).toSet();
    final available = ingredients.where((i) => !used.contains(i['ingredient_id'])).toList();
    if (available.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Every ingredient is already in this recipe. Add new ones from Inventory.')),
      );
      return;
    }
    int ingredientId = available.first['ingredient_id'] as int;
    final qty = TextEditingController();
    final formKey = GlobalKey<FormState>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Add ingredient to recipe'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<int>(
                  initialValue: ingredientId,
                  decoration: const InputDecoration(labelText: 'Ingredient'),
                  items: [
                    for (final i in available)
                      DropdownMenuItem(
                        value: i['ingredient_id'] as int,
                        child: Text('${i['name']} (${i['unit']})'),
                      ),
                  ],
                  onChanged: (v) => setState(() => ingredientId = v ?? ingredientId),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: qty,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Quantity per serving'),
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
              child: const Text('Add'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/menu-items/${widget.menuItemId}/recipe-links', {
        'ingredient_id': ingredientId,
        'quantity_per_serving': qty.text.trim(),
      }),
      success: 'Added to recipe.',
    );
    if (ok) await reload();
  }

  Future<void> _toggleActive(BuildContext context, Json item, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final active = item['is_active'] as bool;
    final ok = await runAction(
      context,
      () => active
          ? api.deleteJson('/menu-items/${widget.menuItemId}')
          : api.putJson('/menu-items/${widget.menuItemId}', {'is_active': true}),
      success: active ? 'Menu item deactivated.' : 'Menu item reactivated.',
    );
    if (ok) await reload();
  }
}

class _SummaryCard extends StatelessWidget {
  final Json item;

  const _SummaryCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final price = asDouble(item['price']);
    final margin = item['profit_margin'];
    final marginValue = margin == null ? null : asDouble(margin);
    final marginPct = (marginValue == null || price == 0) ? null : marginValue / price * 100;
    final active = item['is_active'] as bool;
    final available = item['is_available'] as bool;
    final lowIngredient = item['has_low_stock_ingredient'] == true;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(item['name'] as String, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text('${item['category']}  ·  ${money(price)}'),
            if ((item['description'] as String?)?.isNotEmpty ?? false) ...[
              const SizedBox(height: 8),
              Text(item['description'] as String),
            ],
            const SizedBox(height: 12),
            Text(
              marginValue == null
                  ? 'Profit margin: add recipe ingredients to calculate'
                  : 'Profit margin: ${money(marginValue)} per serving'
                      '${marginPct == null ? '' : ' (${marginPct.toStringAsFixed(0)}%)'}',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (!active) const SeverityChip(label: 'Deactivated', color: Severity.critical),
                SeverityChip(
                  label: available ? 'Available' : 'Unavailable',
                  color: available ? Severity.ok : Severity.critical,
                ),
                if (lowIngredient) const SeverityChip(label: 'Low ingredient', color: Severity.warning),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _EditForm extends StatefulWidget {
  final Json item;
  final Future<void> Function() onSaved;

  const _EditForm({required this.item, required this.onSaved});

  @override
  State<_EditForm> createState() => _EditFormState();
}

class _EditFormState extends State<_EditForm> {
  final _formKey = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.item['name'] as String);
  late final _description = TextEditingController(text: widget.item['description'] as String? ?? '');
  late final _price = TextEditingController(text: trimNum(widget.item['price']));
  late final _category = TextEditingController(text: widget.item['category'] as String);
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _price.dispose();
    _category.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.putJson('/menu-items/${widget.item['menu_item_id']}', {
        'name': _name.text.trim(),
        'description': _description.text.trim(),
        'price': _price.text.trim(),
        'category': _category.text.trim(),
      }),
      success: 'Menu item saved.',
    );
    if (mounted) setState(() => _saving = false);
    if (ok) await widget.onSaved();
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SectionHeader(icon: Icons.edit_rounded, label: 'Edit details'),
          TextFormField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Name'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _description,
            decoration: const InputDecoration(labelText: 'Description (optional)'),
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _price,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Price', prefixText: 'RM '),
            validator: (v) {
              final n = double.tryParse(v?.trim() ?? '');
              if (n == null) return 'Enter a number.';
              if (n <= 0) return 'Price must be greater than zero.';
              return null;
            },
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _category,
            decoration: const InputDecoration(labelText: 'Category'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Save changes'),
          ),
        ],
      ),
    );
  }
}
