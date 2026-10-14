from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsStaffAdmin(BasePermission):
	"""Faqat staff (is_staff) foydalanuvchilar uchun."""

	message = "Bu amal uchun admin huquqi talab qilinadi."

	def has_permission(self, request, view):
		user = request.user
		return bool(user and user.is_authenticated and user.is_staff)


class IsStaffAdminOrReadOnly(BasePermission):
	"""O'qish hamma uchun, yozish faqat staff uchun."""

	def has_permission(self, request, view):
		if request.method in SAFE_METHODS:
			return True
		user = request.user
		return bool(user and user.is_authenticated and user.is_staff)
