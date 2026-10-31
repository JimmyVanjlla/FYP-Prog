import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';
import 'menu_detail_screen.dart';
import 'menu_form_screen.dart';

/// FR2.4 — every authenticated role can view the menu; only the Restaurant
/// Manager can create/edit (server-enforced via require_role — this screen
/// just mirrors that so a non-Manager never sees a control they'd get a 403
/// from anyway). Each item opens its detail (profit margin, recipe, edit).
class MenuListScreen extends StatefulWidget {
  const MenuListScreen({super.key});

  @override
  State<MenuListScreen> createState() => _MenuListScreenState();
}

class _MenuListScreenState extends State<MenuListScreen> {
  bool _showInactive = false;
  int _version = 0;

  Future<List<Json>> _load() async {
    final api = context.read<AuthState>().api;
    return asJsonList(
      await api.getJson('/menu-items', query: {'include_inactive': _showInactive, 'limit': 500}),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isManager = context.watch<AuthState>().role == Roles.manager;

    return AsyncView<List<Json>>(
      key: ValueKey('$_version|$_showInactive'),
      load: _load,
      builder: (context, items, reload) {
        return RefreshableList(
          onRefresh: reload,
          empty: isManager
              ? null
              : const EmptyState(icon: Icons.restaurant_menu_outlined, message: 'No menu items yet.'),
          children: [
            if (isManager)
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Show deactivated items'),
                value: _showInactive,
                onChanged: (v) => setState(() => _showInactive = v),
              ),
            for (final item in items) ...[
              _MenuItemTile(
                item: item,
                onTap: () async {
                  await Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => MenuDetailScreen(menuItemId: item['menu_item_id'] as int)),
                  );
                  if (mounted) setState(() => _version++);
                },
              ),
              const SizedBox(height: 10),
            ],
            if (isManager)
              AddRow(
                label: 'Add menu item',
                onTap: () async {
                  final created = await Navigator.of(
                    context,
                  ).push<bool>(MaterialPageRoute(builder: (_) => const MenuFormScreen()));
                  if (created == true) await reload();
                },
              ),
          ],
        );
      },
    );
  }
}

class _MenuItemTile extends StatelessWidget {
  final Json item;
  final VoidCallback onTap;

  const _MenuItemTile({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final active = item['is_active'] as bool;
    final available = item['is_available'] as bool;
    final lowIngredient = item['has_low_stock_ingredient'] == true;
    final margin = item['profit_margin'];

    final chip = !active
        ? const SeverityChip(label: 'Deactivated', color: Severity.critical)
        : !available
            ? const SeverityChip(label: 'Unavailable', color: Severity.critical)
            : lowIngredient
                ? const SeverityChip(label: 'Low ingredient', color: Severity.warning)
                : const SeverityChip(label: 'Available', color: Severity.ok);

    return Card(
      child: ListTile(
        onTap: onTap,
        leading: IconBadge(
          icon: Icons.restaurant_menu_rounded,
          color: active ? null : Severity.critical,
        ),
        title: Text(item['name'] as String),
        subtitle: Text(
          '${item['category']}  ·  ${money(item['price'])}'
          '${margin == null ? '' : '  ·  margin ${money(margin)}'}',
        ),
        trailing: chip,
      ),
    );
  }
}
