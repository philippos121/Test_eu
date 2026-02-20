import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../../models/chat_message.dart';
import '../../providers/cases_provider.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

class ChatScreen extends ConsumerStatefulWidget {
  final String caseId;
  const ChatScreen({super.key, required this.caseId});
  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _msgCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  bool _sending = false;

  @override
  void dispose() {
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final text = _msgCtrl.text.trim();
    if (text.isEmpty || _sending) return;
    _msgCtrl.clear();
    setState(() => _sending = true);
    try {
      await ref.read(chatProvider(widget.caseId).notifier).sendMessage(text);
      _scrollToBottom();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Fehler: $e'), backgroundColor: AppTheme.danger),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final messagesAsync = ref.watch(chatProvider(widget.caseId));
    final caseAsync = ref.watch(singleCaseProvider(widget.caseId));
    final canChat = caseAsync.valueOrNull?.status.canChat ?? true;

    return Scaffold(
      backgroundColor: const Color(0xFFF0F4FF),
      appBar: AppBar(
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Assistent'),
          caseAsync.when(
            data: (c) => Text(c.title,
                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w400),
                overflow: TextOverflow.ellipsis),
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),
        ]),
        actions: [
          // Show current score
          caseAsync.when(
            data: (c) {
              final p = c.successProbability;
              if (p == null) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(right: 12),
                child: Chip(
                  label: Text(
                    '${(p * 100).toStringAsFixed(0)}%',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: p >= 0.65 ? AppTheme.success : p >= 0.35 ? AppTheme.warning : AppTheme.danger,
                    ),
                  ),
                  backgroundColor: Colors.white,
                  padding: EdgeInsets.zero,
                ),
              );
            },
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: messagesAsync.when(
            loading: () => const LoadingCenter(),
            error: (e, _) => ErrorCenter(error: e),
            data: (messages) {
              _scrollToBottom();
              if (messages.isEmpty) {
                return const Center(
                  child: Text('Starten Sie die Konversation…',
                      style: TextStyle(color: Colors.grey)),
                );
              }
              return ListView.builder(
                controller: _scrollCtrl,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
                itemCount: messages.length,
                itemBuilder: (ctx, i) {
                  final m = messages[i];
                  return _ChatBubble(message: m)
                      .animate()
                      .fadeIn(duration: 200.ms)
                      .slideY(begin: 0.1);
                },
              );
            },
          ),
        ),
        if (_sending)
          const Padding(
            padding: EdgeInsets.only(left: 20, bottom: 4),
            child: Row(children: [
              SizedBox(
                width: 16, height: 16,
                child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.primary),
              ),
              SizedBox(width: 8),
              Text('Assistent schreibt…',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
            ]),
          ),
        _InputBar(
          controller: _msgCtrl,
          onSend: _send,
          enabled: canChat && !_sending,
          hint: canChat ? 'Nachricht eingeben…' : 'Fall abgeschlossen / abgelehnt',
        ),
      ]),
    );
  }
}

class _ChatBubble extends StatelessWidget {
  final ChatMessage message;
  const _ChatBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    return Padding(
      padding: EdgeInsets.only(
        bottom: 12,
        left: isUser ? 48 : 0,
        right: isUser ? 0 : 48,
      ),
      child: Column(
        crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: isUser ? AppTheme.primary : Colors.white,
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(16),
                topRight: const Radius.circular(16),
                bottomLeft: Radius.circular(isUser ? 16 : 4),
                bottomRight: Radius.circular(isUser ? 4 : 16),
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.04),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Text(
              message.content,
              style: TextStyle(
                fontSize: 14,
                color: isUser ? Colors.white : Colors.black87,
                height: 1.45,
              ),
            ),
          ),
          const SizedBox(height: 3),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!isUser) ...[
                const Icon(Icons.smart_toy_outlined, size: 11, color: Colors.grey),
                const SizedBox(width: 3),
              ],
              Text(
                DateFormat('HH:mm').format(message.createdAt),
                style: const TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;
  final bool enabled;
  final String hint;
  const _InputBar({required this.controller, required this.onSend, required this.enabled, required this.hint});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white,
      padding: EdgeInsets.fromLTRB(12, 8, 12, 8 + MediaQuery.of(context).viewPadding.bottom),
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: controller,
            enabled: enabled,
            maxLines: 4,
            minLines: 1,
            textInputAction: TextInputAction.newline,
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(color: Colors.grey),
              filled: true,
              fillColor: Colors.grey.shade100,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(24),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
          ),
        ),
        const SizedBox(width: 8),
        Material(
          color: enabled ? AppTheme.primary : Colors.grey.shade300,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: enabled ? onSend : null,
            child: const Padding(
              padding: EdgeInsets.all(10),
              child: Icon(Icons.send_rounded, color: Colors.white, size: 20),
            ),
          ),
        ),
      ]),
    );
  }
}
