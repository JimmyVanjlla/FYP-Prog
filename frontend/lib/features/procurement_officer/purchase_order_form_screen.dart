import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// FR9.3 / FR9.6 — building a purchase order. Per Ch4 section 4.4.1 the
/// running order total sits beside the line items, and the remaining budget
/// sits beside the total, so nobody has to leave the screen to find the
/// number that decides whether to submit. Going over budget is a warning,
/// not a block (FR9.6): the Manager sees it flagged when approving.
///
/// Quantities pre-fill from the system's purchase recommendations but stay
/// fully editable.
class PurchaseOrderFormScreen extends StatelessWidget {
  const PurchaseOrderFormScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('New purchase order')),
      body: AsyncView<_FormData>(
        load: () async {
          final results = await Future.wait([
            api.getJson('/procurement/suppliers', query: {'limit': 500}),
            api.getJson('/procurement/suppliers/pricing', query: {'limit': 500}),
            api.getJson('/inventory/ingredients', query: {'limit': 500}),
            api.getJson('/procurement/recommendations', query: {'limit': 200}),
            api.getJson('/procurement/budget/utilisation'),
          ]);
          return _FormData(
            suppliers: asJsonList(results[0]).where((s) => s['is_active'] == true).toList(),
            pricing: asJsonList(results[1]),
            ingredients: {for (final i in asJsonList(results[2])) i['ingredient_id'] as int: i},
            recommendations: asJsonList(results[3]),
            remainingBudget: asDouble(asJson(results[4])['remaining']),
          );
        },
        builder: (context, data, _) => _OrderForm(data: data),
      ),
    );
  }
}

class _FormData {
  final List<Json> suppliers;
  final List<Json> pricing;
  final Map<int, Json> ingredients;
  final List<Json> recommendations;
  final double remainingBudget;

  _FormData({
    required this.suppliers,
    required this.pricing,
    required this.ingredients,
    required this.recommendations,
    required this.remainingBudget,
  });
}

class _Line {
  int? ingredientId;
  final TextEditingController quantity = TextEditingController();

  _Line({this.ingredientId, String? quantity}) {
    if (quantity != null) this.quantity.text = quantity;
  }
}

class _OrderForm extends StatefulWidget {
  final _FormData data;

  const _OrderForm({required this.data});

  @override
  State<_OrderForm> createState() => _OrderFormState();
}

class _OrderFormState extends State<_OrderForm> {
  int? _supplierId;
  final List<_Line> _lines = [];
  bool _submitting = false;

  _FormData get d => widget.data;

  @override
  void initState() {
    super.initState();
    if (d.suppliers.isNotEmpty) _supplierId = d.suppliers.first['supplier_id'] as int;
    _prefillFromRecommendations();
  }

  @override
  void dispose() {
    for (final l in _lines) {
      l.quantity.dispose();
    }
    super.dispose();
  }

  /// ingredient_id -> this supplier's unit price.
  Map<int, double> get _prices => {
    for (final p in d.pricing)
      if (p['supplier_id'] == _supplierId) p['ingredient_id'] as int: asDouble(p['unit_price']),
  };

  void _prefillFromRecommendations() {
    for (final l in _lines) {
      l.quantity.dispose();
    }
    _lines.clear();
    final prices = _prices;
    for (final r in d.recommendations) {
      final id = r['ingredient_id'] as int;
      if (prices.containsKey(id)) {
        _lines.add(_Line(ingredientId: id, quantity: trimNum(r['recommended_quantity'])));
      }
    }
  }

  double _lineCost(_Line line) {
    final qty = double.tryParse(line.quantity.text.trim()) ?? 0;
    final price = _prices[line.ingredientId] ?? 0;
    return qty > 0 ? qty * price : 0;
  }

  double get _total => _lines.fold(0, (sum, l) => sum + _lineCost(l));

  bool get _valid =>
      _supplierId != null &&
      _lines.isNotEmpty &&
      _lines.every(
        (l) => l.ingredientId != null && (double.tryParse(l.quantity.text.trim()) ?? 0) > 0,
      );

  Future<void> _submit() async {
    setState(() => _submitting = true);
    final api = context.read<AuthState>().api;
    Json? created;
    final ok = await runAction(context, () async {
      created = asJson(
        await api.postJson('/procurement/purchase-orders', {
          'supplier_id': _supplierId,
          'line_items': [
            for (final l in _lines) {'ingredient_id': l.ingredientId, 'quantity': l.quantity.text.trim()},
          ],
        }),
      );
    });
    if (!mounted) return;
    setState(() => _submitting = false);
    if (ok) {
      final over = created?['exceeds_budget'] == true;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            over
                ? 'Order submitted for approval. It exceeds the remaining budget, which the Manager will see.'
                : 'Order submitted for approval.',
          ),
        ),
      );
      Navigator.of(context).pop(true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (d.suppliers.isEmpty) {
      return const EmptyState(
        icon: Icons.storefront_outlined,
        message: 'No active suppliers.',
        detail: 'Add a supplier and its prices first.',
      );
    }
    final prices = _prices;
    final over = _total > d.remainingBudget;
    final scheme = Theme.of(context).colorScheme;

    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              DropdownButtonFormField<int>(
                initialValue: _supplierId,
                decoration: const InputDecoration(labelText: 'Supplier'),
                items: [
                  for (final s in d.suppliers)
                    DropdownMenuItem(value: s['supplier_id'] as int, child: Text(s['name'] as String)),
                ],
                onChanged: (v) => setState(() {
                  _supplierId = v;
                  _prefillFromRecommendations();
                }),
              ),
              const SizedBox(height: 16),
              SectionHeader(icon: Icons.list_alt_rounded, label: 'Items', trailing: '${_lines.length}'),
              if (prices.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('This supplier has no prices set yet, so there is nothing to order from them.'),
                ),
              for (var i = 0; i < _lines.length; i++) ...[
                _LineEditor(
                  line: _lines[i],
                  prices: prices,
                  ingredients: d.ingredients,
                  cost: _lineCost(_lines[i]),
                  usedElsewhere: {
                    for (var j = 0; j < _lines.length; j++)
                      if (j != i && _lines[j].ingredientId != null) _lines[j].ingredientId!,
                  },
                  onChanged: () => setState(() {}),
                  onRemove: () => setState(() {
                    _lines[i].quantity.dispose();
                    _lines.removeAt(i);
                  }),
                ),
                const SizedBox(height: 10),
              ],
              if (prices.isNotEmpty)
                AddRow(
                  label: 'Add item',
                  onTap: () {
                    final used = _lines.map((l) => l.ingredientId).toSet();
                    final next = prices.keys.where((id) => !used.contains(id));
                    if (next.isEmpty) return;
                    setState(() => _lines.add(_Line(ingredientId: next.first)));
                  },
                ),
              if (d.recommendations.isNotEmpty && prices.isNotEmpty)
                TextButton.icon(
                  onPressed: () => setState(_prefillFromRecommendations),
                  icon: const Icon(Icons.auto_awesome_rounded, size: 18),
                  label: const Text('Reset to the recommended quantities'),
                ),
            ],
          ),
        ),
        Material(
          elevation: 8,
          color: scheme.surfaceContainer,
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      const Expanded(child: Text('Order total', style: TextStyle(fontWeight: FontWeight.w700))),
                      Text(
                        money(_total),
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          over
                              ? 'Over the remaining budget of ${money(d.remainingBudget)} by ${money(_total - d.remainingBudget)}'
                              : 'Remaining budget ${money(d.remainingBudget)}: ${money(d.remainingBudget - _total)} left after this order',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: over ? Severity.critical : scheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                      if (over) const SeverityChip(label: 'Exceeds budget', color: Severity.critical),
                    ],
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: _valid && !_submitting ? _submit : null,
                    child: _submitting
                        ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Submit for approval'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _LineEditor extends StatelessWidget {
  final _Line line;
  final Map<int, double> prices;
  final Map<int, Json> ingredients;
  final double cost;
  final Set<int> usedElsewhere;
  final VoidCallback onChanged;
  final VoidCallback onRemove;

  const _LineEditor({
    required this.line,
    required this.prices,
    required this.ingredients,
    required this.cost,
    required this.usedElsewhere,
    required this.onChanged,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final options = prices.keys.where((id) => id == line.ingredientId || !usedElsewhere.contains(id)).toList();
    final unit = ingredients[line.ingredientId]?['unit'] ?? '';
    final qty = double.tryParse(line.quantity.text.trim());
    final qtyError = line.quantity.text.trim().isEmpty
        ? null
        : (qty == null ? 'Enter a number.' : (qty <= 0 ? 'Must be above zero.' : null));

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<int>(
                    initialValue: line.ingredientId,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Ingredient'),
                    items: [
                      for (final id in options)
                        DropdownMenuItem(
                          value: id,
                          child: Text(
                            '${ingredients[id]?['name'] ?? 'Ingredient #$id'}  ·  ${money(prices[id])}/${ingredients[id]?['unit'] ?? ''}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: (v) {
                      line.ingredientId = v;
                      onChanged();
                    },
                  ),
                ),
                IconButton(
                  tooltip: 'Remove item',
                  icon: const Icon(Icons.close_rounded),
                  onPressed: onRemove,
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: line.quantity,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    onChanged: (_) => onChanged(),
                    decoration: InputDecoration(labelText: 'Quantity', suffixText: unit as String, errorText: qtyError),
                  ),
                ),
                const SizedBox(width: 16),
                Text(money(cost), style: const TextStyle(fontWeight: FontWeight.w700)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
