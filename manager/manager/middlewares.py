from django.utils import translation


def language_middleware(get_response):
    def middleware(request):
        request_lang = translation.get_language_from_request(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.profile:
            translation.activate(user.profile.get_language(request_lang=request_lang))
        else:
            translation.activate(request_lang)
        response = get_response(request)
        translation.deactivate()
        return response

    return middleware
