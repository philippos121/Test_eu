class AppUser {
  final String id;
  final String email;
  final String fullName;
  final String language;
  final bool isAdmin;
  final DateTime createdAt;

  const AppUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.language,
    required this.isAdmin,
    required this.createdAt,
  });

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: j['id'] as String,
        email: j['email'] as String,
        fullName: j['full_name'] as String,
        language: j['language'] as String? ?? 'de',
        isAdmin: j['is_admin'] as bool? ?? false,
        createdAt: DateTime.parse(j['created_at'] as String),
      );

  String get initials {
    final parts = fullName.split(' ');
    if (parts.length >= 2) return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    return fullName.isNotEmpty ? fullName[0].toUpperCase() : '?';
  }
}
