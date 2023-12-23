import datetime
import json

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from manager.builder import prepare_builder_for_collection
from manager.kiwix_library import catalog
from manager.models import Configuration, Media, Organization, Profile
from manager.utils import ONE_GB, human_readable_size


def packages_for_language(request, lang_code):
    order_by_size: bool = request.GET.get("order") == "size"
    if not order_by_size:
        return JsonResponse(
            {"books": [book.to_dict() for book in catalog.get_for_lang(lang_code)]}
        )
    return JsonResponse(
        {
            "books": sorted(
                [book.to_dict() for book in catalog.get_for_lang(lang_code)],
                key=lambda book: book["size"],
                reverse=True,
            )
        }
    )


@csrf_exempt
@require_POST
def required_size_for_config(request):
    try:
        payload = request.body
        if isinstance(payload, bytes):
            payload = payload.decode("UTF-8")
        data = json.loads(payload)
    except Exception:
        return JsonResponse({"error": str(request.body)})

    # check disk space
    builder = prepare_builder_for_collection(
        edupi=data.get("edupi", False),
        edupi_resources=data.get("edupi_resources", None),
        nomad=data.get("nomad", False),
        mathews=data.get("mathews", False),
        africatik=data.get("africatik", False),
        africatikmd=data.get("africatikmd", False),
        metrics=data.get("metrics", False),
        packages=data.get("packages", []),
        wikifundi_languages=data.get("wikifundi", []),
    )
    required_image_size = builder.get_min_size()
    media = Media.get_min_for(required_image_size)
    return JsonResponse(
        {
            "size": required_image_size,
            "hsize": human_readable_size(required_image_size, binary=False),
            "media_size": human_readable_size(media.size * ONE_GB, binary=False)
            if media
            else None,
            "hfree": human_readable_size(media.bytes - required_image_size)
            if media
            else None,
        }
    )


def media_choices_for_configuration(request, config_id):
    all_medias = Media.objects.all()

    config = Configuration.get_or_none(config_id)
    if config is not None and config.organization == request.user.profile.organization:
        medias = [m for m in all_medias if m.bytes >= config.size]
    if not medias:
        medias = all_medias.filter(size=all_medias.aggregate(Max("size"))["size__max"])
    return JsonResponse(Media.choices_for(medias), safe=False)


@csrf_exempt
@require_POST
def create_user_account(request):
    """create a user account automatically from an email address

    - must be authenticated via a `Token: {ACCOUNTS_API_TOKEN}` header
    - JSON payload must include an `email` field
    - optionnal payload fields:
      - username: used instead of email if provided
      - name: used instead of email if provided
      - password: used instead of auto-generated one is provided
    - returns a {"username": str, password: str} payload"""
    if request.headers.get("Token") != settings.ACCOUNTS_API_TOKEN:
        return JsonResponse({"error": "PermissionDenied"}, status=403)

    try:
        payload = request.body
        if not payload:
            raise ValueError("Missing payload")
        if isinstance(payload, bytes):
            payload = payload.decode("UTF-8")
        data = json.loads(payload)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    # email is mandatory
    email = str(data.get("email", "")) or None
    if not email:
        return JsonResponse({"error": "missing required email"}, status=400)

    # parse expiry if provided
    expiry = data.get("expiry")
    if expiry:
        try:
            expiry = datetime.datetime.fromisoformat(expiry)
        except Exception:
            return JsonResponse({"error": "Unable to parse expiry date"}, status=400)

    limited = bool(data.get("limited", True))

    name = str(data.get("name", email.split("@")[0]))
    username = str(data.get("username", email))
    password = str(data.get("password", "")) or None
    if not password:
        password = User.objects.make_random_password(length=8)

    if (
        User.objects.filter(username=username).count()
        or Organization.objects.filter(slug=username).count()
    ):
        return JsonResponse(
            {"error": f"Username `{username}` is already taken"}, status=409
        )

    if Profile.taken(email):
        account = Profile.objects.filter(user__email=email).first()
        if expiry and account.expire_on is not None:
            account.expire_on = expiry
            account.save()
        return JsonResponse(
            {"error": f"Email `{email}` already has an account ({account.username})"},
            status=409,
        )

    # good to go, create an Organization, User and Profile
    try:
        org = None
        org = Organization.objects.create(
            slug=username,
            name="Single" if username == name else name,
            email=email,
            units=102400 if limited else None,
        )
        profile = Profile.create(
            organization=org,
            first_name=name,
            email=email,
            username=username,
            password=password,
            is_admin=False,
            expiry=expiry,
            can_order_physical=False,
        )
    except Exception as exc:
        if org:
            try:
                org.delete()
            except Exception:
                ...
        return JsonResponse({"error": f"Failed to create account: {exc}"}, status=500)

    return JsonResponse(
        {
            "username": profile.username,
            "password": password,
            "name": profile.name,
        },
        status=201,
    )
