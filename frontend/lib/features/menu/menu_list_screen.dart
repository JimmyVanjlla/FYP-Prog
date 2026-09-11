import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/theme.dart';
import '../../models/menu_item.dart';
import 'menu_form_screen.dart';

/// FR2.4 — every authenticated role can view the menu; only the Restaurant
/// Manager can create/edit (server-enforced via require_role — this screen
/// just mirrors that so a non-Manager never sees a control they'd get a 403
/// from anyway).
class MenuListScreen extends StatefulWidget {
  const MenuListScreen({super.key});

  @override
  State<MenuListScreen> createState() => _MenuListScreenState();
}

class _MenuListScreenState extends State<MenuListScreen> {
  late Future<List<MenuItem>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<MenuItem>> _load() async {
    final api = context.read<AuthState>().api;
    final raw = await api.listMenuItems();
    return raw.map((e) => MenuItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    final isManager = context.watch<AuthState>().role == Roles.manager;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Menu'),
        actions: [
          IconButton(
            tooltip: 'Log out',
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<AuthState>().logout(),
          ),
        ],
      ),
      body: FutureBuilder<List<MenuItem>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            final message =
                snapshot.error is ApiException ? (snapshot.error as ApiException).message : 'Failed to load menu.';
            return Center(child: Text(message));
          }
          final items = snapshot.data ?? [];
          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: items.length + (isManager ? 1 : 0),
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                // Ch4 §4.4.1: the "+ add" row is the same reused pattern
                // used everywhere else something can be added (e.g. later,
                // "+ Assign staff" on the Schedule Builder screen).
                if (isManager && index == items.length) {
                  return _AddMenuItemRow(onAdded: _refresh);
                }
                return _MenuItemTile(item: items[index]);
              },
            ),
          );
        },
      ),
    );
  }
}

class _MenuItemTile extends StatelessWidget {
  final MenuItem item;

  const _MenuItemTile({required this.item});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(item.name),
        subtitle: Text('${item.category} · RM ${item.price}'),
        trailing: SeverityChip(
          label: item.isAvailable ? 'Available' : 'Unavailable',
          color: item.isAvailable ? Severity.ok : Severity.critical,
        ),
      ),
    );
  }
}

class _AddMenuItemRow extends StatelessWidget {
  final Future<void> Function() onAdded;

  const _AddMenuItemRow({required this.onAdded});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: () async {
        final created = await Navigator.of(context).push<bool>(
          MaterialPageRoute(builder: (_) => const MenuFormScreen()),
        );
        if (created == true) await onAdded();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          border: Border.all(
            color: Theme.of(context).colorScheme.outline,
            style: BorderStyle.solid,
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        alignment: Alignment.center,
        child: const Text('+ Add menu item'),
      ),
    );
  }
}
