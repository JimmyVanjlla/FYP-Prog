import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../models/menu_item.dart';

/// Module 5 — FR5.3: Kitchen Staff log end-of-service leftover quantities.
/// (Prep recommendation/confirmation, FR5.1-FR5.2/FR5.5, is implemented and
/// tested at the API level — see backend/tests/test_kitchen.py — and gets
/// a matching screen once Staff Scheduling's shift-based UI shell lands in
/// Sprint 3, so leftover logging isn't duplicated across two screens.)
class LeftoverLogScreen extends StatefulWidget {
  const LeftoverLogScreen({super.key});

  @override
  State<LeftoverLogScreen> createState() => _LeftoverLogScreenState();
}

class _LeftoverLogScreenState extends State<LeftoverLogScreen> {
  final _formKey = GlobalKey<FormState>();
  final _preparedController = TextEditingController();
  final _leftoverController = TextEditingController();
  DateTime _serviceDate = DateTime.now();
  String _leftoverLevel = 'Partially Eaten';
  MenuItem? _selectedItem;

  late Future<List<MenuItem>> _menuFuture;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _menuFuture = _loadMenu();
  }

  Future<List<MenuItem>> _loadMenu() async {
    final api = context.read<AuthState>().api;
    final raw = await api.listMenuItems();
    return raw
        .map((e) => MenuItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  void dispose() {
    _preparedController.dispose();
    _leftoverController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || _selectedItem == null) return;
    setState(() => _submitting = true);
    try {
      final api = context.read<AuthState>().api;
      await api.logLeftover(
        menuItemId: _selectedItem!.menuItemId,
        servicePeriodDate:
            '${_serviceDate.year.toString().padLeft(4, '0')}-${_serviceDate.month.toString().padLeft(2, '0')}-${_serviceDate.day.toString().padLeft(2, '0')}',
        preparedQuantity: _preparedController.text.trim(),
        leftoverQuantity: _leftoverController.text.trim(),
        leftoverLevel: _leftoverLevel,
      );
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Leftover log saved.')));
        _preparedController.clear();
        _leftoverController.clear();
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<MenuItem>>(
      future: _menuFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snapshot.data ?? [];
        _selectedItem ??= items.isNotEmpty ? items.first : null;

        return Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Form(
                key: _formKey,
                autovalidateMode: AutovalidateMode.onUserInteraction,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Log end-of-service leftovers',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 16),
                    DropdownButtonFormField<MenuItem>(
                      initialValue: _selectedItem,
                      decoration: const InputDecoration(labelText: 'Dish'),
                      items: items
                          .map(
                            (m) =>
                                DropdownMenuItem(value: m, child: Text(m.name)),
                          )
                          .toList(),
                      onChanged: (v) => setState(() => _selectedItem = v),
                    ),
                    const SizedBox(height: 16),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Service date'),
                      subtitle: Text(
                        '${_serviceDate.year}-${_serviceDate.month.toString().padLeft(2, '0')}-${_serviceDate.day.toString().padLeft(2, '0')}',
                      ),
                      trailing: const Icon(Icons.calendar_today),
                      onTap: () async {
                        final picked = await showDatePicker(
                          context: context,
                          initialDate: _serviceDate,
                          firstDate: DateTime(2020),
                          lastDate: DateTime(2100),
                        );
                        if (picked != null) {
                          setState(() => _serviceDate = picked);
                        }
                      },
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      controller: _preparedController,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Quantity prepared',
                      ),
                      validator: (v) {
                        final parsed = num.tryParse(v?.trim() ?? '');
                        if (parsed == null || parsed <= 0) {
                          return 'Must be a number greater than zero.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _leftoverController,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Quantity left over',
                      ),
                      // Mirrors the backend's leftover<=prepared check
                      // (surfaced inline, at point of entry).
                      validator: (v) {
                        final parsed = num.tryParse(v?.trim() ?? '');
                        if (parsed == null || parsed < 0) {
                          return 'Must be a number ≥ 0.';
                        }
                        final prepared = num.tryParse(
                          _preparedController.text.trim(),
                        );
                        if (prepared != null && parsed > prepared) {
                          return 'Cannot exceed quantity prepared.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                    DropdownButtonFormField<String>(
                      initialValue: _leftoverLevel,
                      decoration: const InputDecoration(
                        labelText: 'Leftover level',
                      ),
                      items: const ['Partially Eaten', 'Mostly Uneaten']
                          .map(
                            (l) => DropdownMenuItem(value: l, child: Text(l)),
                          )
                          .toList(),
                      onChanged: (v) =>
                          setState(() => _leftoverLevel = v ?? _leftoverLevel),
                    ),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: (_submitting || _selectedItem == null)
                          ? null
                          : _submit,
                      child: _submitting
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Save log'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
