enum MessageRole { user, assistant, system;
  static MessageRole fromString(String s) {
    if (s == 'assistant') return MessageRole.assistant;
    if (s == 'system') return MessageRole.system;
    return MessageRole.user;
  }
}

class ChatMessage {
  final String id;
  final MessageRole role;
  final String content;
  final String? step;
  final DateTime createdAt;

  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    this.step,
    required this.createdAt,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
        id: j['id'] as String,
        role: MessageRole.fromString(j['role'] as String),
        content: j['content'] as String,
        step: j['step'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
      );

  bool get isUser => role == MessageRole.user;
  bool get isAssistant => role == MessageRole.assistant;
}
