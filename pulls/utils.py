import re
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions
from .models import Users, UserTwoFactorAuthData
from six import text_type
import pyotp  # type: ignore
from django.shortcuts import redirect
from functools import wraps
from django.utils.decorators import method_decorator


USERNAME_MIN_LENGTH = 9


def is_valid_username(username):
    if get_user_model().objects.filter(username=username).exists():
        return False
    if not username.lower().startswith("cpe"):
        return False
    if len(username.replace("/", "")) < USERNAME_MIN_LENGTH:
        return False
    if not username.isalnum():
        return False
    return True


def is_valid_password(password, user):
    try:
        validate_password(password, user=user)
    except exceptions.ValidationError:
        return False
    return True


def is_valid_email(email):
    if Users.objects.filter(users_mail=email).exists():
        return {
            "success": False,
            "reason": "Cette adresse mail existe dans nos archives, merci.",
        }
    print(email)
    print(re.match(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", email))
    if not re.match(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", email):
        return {
            "success": False,
            "reason": "Le format de votre adresse email est incorrect, merci de verifier votre adresse",
        }
    if email is None:
        return {
            "success": False,
            "reason": "Adresse mail inexitant",
        }
    return {
        "success": True,
    }


def validate_email(email):
    if Users.objects.filter(users_mail=email).exists():
        return {"success": False, "reason": "Email Address already exists"}
    if not re.match(r"^\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$", email):
        return {"success": False, "reason": "Invalid Email Address"}
    if email is None:
        return {"success": False, "reason": "Email is required."}
    return {"success": True}


def validate_username(username):
    if get_user_model().objects.filter(username=username).exists():
        return {
            "success": False,
            "reason": "L'utilisateur avec ce numéro d'immatriculation existe déjà",
        }
    if not isinstance(username, text_type):
        return {
            "success": False,
            "reason": "Le numéro d'immatriculation doit être alphanumérique",
        }

    if len(username.replace("/", "")) < USERNAME_MIN_LENGTH:
        return {
            "success": False,
            "reason": "Numéro de matricule trop long",
        }

    if not username.isalnum():
        return {
            "success": False,
            "reason": "Le numéro d'immatriculation doit être alphanumérique",
        }

    if not username.lower().startswith("cpe"):
        return {
            "success": False,
            "reason": "Le numéro de matricule n'est pas valide",
        }

    return {
        "success": True,
    }


def user_two_factor_auth_data_create(*, user) -> UserTwoFactorAuthData:
    if hasattr(user, 'two_factor_auth_data'):
        raise ValidationError(
            'Ne peut pas avoir plus d’une donnée liée à 2FA.'
        )

    two_factor_auth_data = UserTwoFactorAuthData.objects.create(
        user=user,
        otp_secret=pyotp.random_base32(),
    )
    print(two_factor_auth_data) 
    return two_factor_auth_data

def AdminSetupTwoFactorAuthView(user):
    context = {}
    try:
        two_factor_auth_data = user_two_factor_auth_data_create(user=user)
        otp_secret = two_factor_auth_data.otp_secret

        context["otp_secret"] = otp_secret
        context["qr_code"] = two_factor_auth_data.generate_qr_code(
                name=user.users_mail
            )
    except ValidationError as exc:
        context["form_errors"] = exc.message
    return context


def login_required_connect(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('login')

        try:
            user = Users.objects.get(id_user=user_id)
        except Users.DoesNotExist:
            return redirect('login')

        request.user = user
        return view_func(request, *args, **kwargs)
    return _wrapped_view


class CustomLoginRequiredMixin:
    @method_decorator(login_required_connect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


# Decorator to verify user type
def utilisateur_autorise(types_autorises):
    def decorateur(vue_fonction):
        @wraps(vue_fonction)
        def vue_modifiee(request, *args, **kwargs):
            if not hasattr(request, 'user'):
                return HttpResponseForbidden("Vous n'êtes pas autorisé à accéder à cette page")

            match request.user.users_type:
                case 'paie':
                    users_type = "Ressources humaines"
                case 'admin':
                    users_type = "Direction"
                case 'stt':
                    users_type = "Freelance"
                case 'con':
                    users_type = "Consultant"
                case 'com':
                    users_type = "Commerciaux"
                case 'sup':
                    users_type = "Super admin"
                case _:
                    users_type = "Inconnu"

            if users_type not in types_autorises:
                return HttpResponseForbidden("Vous n'êtes pas autorisé à accéder à cette page")

            return vue_fonction(request, *args, **kwargs)
        return vue_modifiee
    return decorateur


class AdminRequiredMixin:
    @method_decorator(login_required_connect)
    @method_decorator(utilisateur_autorise(['admin', 'sup']))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
