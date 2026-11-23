PROPRIETARIO = 'Proprietário'
VENDEDOR = 'Vendedor'
PERFIS = [(VENDEDOR, 'Vendedor'), (PROPRIETARIO, 'Proprietário')]


def eh_proprietario(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=PROPRIETARIO).exists()


def perfil_do_usuario(user):
    if user.is_superuser:
        return PROPRIETARIO
    nomes = {g.name for g in user.groups.all()}
    if PROPRIETARIO in nomes:
        return PROPRIETARIO
    if VENDEDOR in nomes:
        return VENDEDOR
    return 'Sem perfil'