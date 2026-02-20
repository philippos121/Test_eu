import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:toastification/toastification.dart';
import '../../providers/auth_provider.dart';
import '../../theme.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});
  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _passConfirmCtrl = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _passConfirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      await ref.read(authProvider.notifier).register(
            _emailCtrl.text.trim(),
            _passCtrl.text,
            _nameCtrl.text.trim(),
          );
    } catch (e) {
      if (mounted) {
        toastification.show(
          context: context,
          title: const Text('Registrierung fehlgeschlagen'),
          description: Text(e.toString()),
          type: ToastificationType.error,
          autoCloseDuration: const Duration(seconds: 4),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: AppTheme.primary,
        elevation: 0,
        title: const Text('Registrieren', style: TextStyle(color: AppTheme.primary)),
        leading: BackButton(onPressed: () => context.go('/auth/login')),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(children: [
              TextFormField(
                controller: _nameCtrl,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Vollständiger Name',
                  prefixIcon: Icon(Icons.person_outline),
                ),
                validator: (v) => v != null && v.length >= 2 ? null : 'Name erforderlich',
              ).animate().fadeIn(delay: 100.ms),
              const SizedBox(height: 16),
              TextFormField(
                controller: _emailCtrl,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'E-Mail',
                  prefixIcon: Icon(Icons.email_outlined),
                ),
                validator: (v) => v != null && v.contains('@') ? null : 'Ungültige E-Mail',
              ).animate().fadeIn(delay: 150.ms),
              const SizedBox(height: 16),
              TextFormField(
                controller: _passCtrl,
                obscureText: true,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Passwort',
                  prefixIcon: Icon(Icons.lock_outline),
                ),
                validator: (v) => v != null && v.length >= 6 ? null : 'Mindestens 6 Zeichen',
              ).animate().fadeIn(delay: 200.ms),
              const SizedBox(height: 16),
              TextFormField(
                controller: _passConfirmCtrl,
                obscureText: true,
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => _register(),
                decoration: const InputDecoration(
                  labelText: 'Passwort bestätigen',
                  prefixIcon: Icon(Icons.lock_outline),
                ),
                validator: (v) =>
                    v == _passCtrl.text ? null : 'Passwörter stimmen nicht überein',
              ).animate().fadeIn(delay: 250.ms),
              const SizedBox(height: 28),
              FilledButton(
                onPressed: _loading ? null : _register,
                child: _loading
                    ? const SizedBox(
                        width: 20, height: 20,
                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                      )
                    : const Text('Konto erstellen'),
              ).animate().fadeIn(delay: 300.ms),
              const SizedBox(height: 12),
              TextButton(
                onPressed: () => context.go('/auth/login'),
                child: const Text('Bereits registriert? Anmelden'),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
