from .perfis import eh_proprietario


def perfil(request):
    return {'eh_proprietario': eh_proprietario(request.user)}