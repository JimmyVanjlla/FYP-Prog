import 'package:flutter/material.dart';

import 'api_client.dart';
import 'theme.dart';

/// Turns an error from the API client into something a person can read.
String describeError(Object error, [String fallback = 'Something went wrong.']) {
  if (error is ApiException) return error.message;
  return 'Could not reach the server. Please try again.';
}

/// Loads data once, shows a spinner / a retryable error / the content, and
/// hands the builder a `reload` callback for pull-to-refresh and for
/// refreshing after a mutation. Replaces the FutureBuilder + RefreshIndicator
/// boilerplate every list screen would otherwise repeat.
class AsyncView<T> extends StatefulWidget {
  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  const AsyncView({super.key, required this.load, required this.builder});

  @override
  State<AsyncView<T>> createState() => _AsyncViewState<T>();
}

class _AsyncViewState<T> extends State<AsyncView<T>> {
  late Future<T> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.load();
  }

  Future<void> _reload() async {
    final next = widget.load();
    setState(() {
      _future = next;
    });
    try {
      await next;
    } catch (_) {
      // The error state is rendered by the FutureBuilder below.
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                EmptyState(
                  icon: Icons.cloud_off_rounded,
                  message: describeError(snapshot.error!),
                ),
                OutlinedButton.icon(
                  onPressed: _reload,
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Try again'),
                ),
              ],
            ),
          );
        }
        return widget.builder(context, snapshot.data as T, _reload);
      },
    );
  }
}

/// A pull-to-refresh list that shows [empty] when there's nothing to list.
class RefreshableList extends StatelessWidget {
  final Future<void> Function() onRefresh;
  final List<Widget> children;
  final Widget? empty;
  final EdgeInsets padding;

  const RefreshableList({
    super.key,
    required this.onRefresh,
    required this.children,
    this.empty,
    this.padding = const EdgeInsets.all(16),
  });

  @override
  Widget build(BuildContext context) {
    final showEmpty = children.isEmpty && empty != null;
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: padding,
        children: showEmpty ? [const SizedBox(height: 80), empty!] : children,
      ),
    );
  }
}

/// Runs a mutation, surfaces any failure as a snackbar, and reports whether
/// it succeeded so the caller can reload.
Future<bool> runAction(
  BuildContext context,
  Future<dynamic> Function() action, {
  String? success,
}) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    await action();
    if (success != null) {
      messenger.showSnackBar(SnackBar(content: Text(success)));
    }
    return true;
  } catch (e) {
    messenger.showSnackBar(SnackBar(content: Text(describeError(e))));
    return false;
  }
}
