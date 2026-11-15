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
/// The menu split the way the ingredient list is: what cannot be served first,
/// then dishes with a low ingredient, then the ones that are fine, and
/// deactivated dishes (only shown on request) last. A to Z within each group.
({List<Json> unavailable, List<Json> low, List<Json> available, List<Json> deactivated}) groupMenu(List<Json> items) {
  int byName(Json a, Json b) => (a['name'] as String).toLowerCase().compareTo((b['name'] as String).toLowerCase());
  final unavailable = <Json>[], low = <Json>[], available = <Json>[], deactivated = <Json>[];
  for (final item in items) {
    if (item['is_active'] != true) {
      deactivated.add(item);
    } else if (item['is_available'] != true) {
      unavailable.add(item);
    } else if (item['has_low_stock_ingredient'] == true) {
      low.add(item);
    } else {
      available.add(item);
    }
  }
  for (final group in [unavailable, low, available, deactivated]) {
    group.sort(byName);
  }
  return (unavailable: unavailable, low: low, available: available, deactivated: deactivated);
}

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
        final groups = groupMenu(items);
        Widget tile(Json item) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _MenuItemTile(
            item: item,
            onTap: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => MenuDetailScreen(menuItemId: item['menu_item_id'] as int)),
              );
              if (mounted) setState(() => _version++);
            },
          ),
        );
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
            if (items.isNotEmpty) ...[
              Row(
                children: [
                  Expanded(
                    child: StatTile(
                      icon: groups.low.isEmpty && groups.unavailable.isEmpty ? Icons.check_circle_rounded : Icons.warning_amber_rounded,
                      value: '${groups.low.length + groups.unavailable.length}',
                      label: 'Low ingredient',
                      color: groups.low.isEmpty && groups.unavailable.isEmpty ? Severity.ok : Severity.warning,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatTile(
                      icon: Icons.check_circle_rounded,
                      value: '${groups.available.length}',
                      label: 'Available',
                      color: Severity.ok,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: StatTile(
                      icon: Icons.restaurant_menu_rounded,
                      value: '${items.length - groups.deactivated.length}',
                      label: 'Dishes',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
            ],
            if (groups.unavailable.isNotEmpty) ...[
              SectionHeader(
                icon: Icons.error_rounded,
                label: 'Unavailable: out of an ingredient',
                trailing: '${groups.unavailable.length}',
                color: Severity.critical,
              ),
              for (final item in groups.unavailable) tile(item),
              const SizedBox(height: 8),
            ],
            if (groups.low.isNotEmpty) ...[
              SectionHeader(
                icon: Icons.warning_amber_rounded,
                label: 'Low ingredient: restock soon',
                trailing: '${groups.low.length}',
                color: Severity.warning,
              ),
              for (final item in groups.low) tile(item),
              const SizedBox(height: 8),
            ],
            if (groups.available.isNotEmpty) ...[
              SectionHeader(
                icon: Icons.check_circle_rounded,
                label: 'Available',
                trailing: '${groups.available.length}',
                color: Severity.ok,
              ),
              for (final item in groups.available) tile(item),
              const SizedBox(height: 8),
            ],
            if (groups.deactivated.isNotEmpty) ...[
              SectionHeader(
                icon: Icons.visibility_off_rounded,
                label: 'Deactivated',
                trailing: '${groups.deactivated.length}',
                color: Severity.critical,
              ),
              for (final item in groups.deactivated) tile(item),
              const SizedBox(height: 8),
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
