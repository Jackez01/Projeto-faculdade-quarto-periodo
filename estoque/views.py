from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    CategoriaForm, FiltroMovimentacaoForm, MovimentacaoForm, NovaSenhaForm,
    ProdutoForm, UsuarioCreateForm, UsuarioEditForm,
)
from .models import Categoria, Movimentacao, Produto
from .perfis import eh_proprietario, perfil_do_usuario

User = get_user_model()

AJUDA_SENHA = 'A senha precisa ter pelo menos 8 caracteres e não pode ser só números nem uma senha muito comum.'


def proprietario_required(view):
    """Só deixa passar o proprietário. Os demais voltam para a lista de produtos com um aviso."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not eh_proprietario(request.user):
            messages.error(request, 'Apenas o proprietário pode acessar essa página.')
            return redirect('produto_list')
        return view(request, *args, **kwargs)
    return wrapper


# ---------- Categorias ----------

@login_required
def categoria_list(request):
    categorias = Categoria.objects.annotate(total_produtos=Count('produtos')).order_by('nome')
    return render(request, 'estoque/categoria_list.html', {
        'categorias': categorias,
        'pode_editar': eh_proprietario(request.user),
    })


@proprietario_required
def categoria_create(request):
    form = CategoriaForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria cadastrada.')
        return redirect('categoria_list')
    return render(request, 'estoque/categoria_form.html', {'form': form, 'titulo': 'Nova categoria'})


@proprietario_required
def categoria_update(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria atualizada.')
        return redirect('categoria_list')
    return render(request, 'estoque/categoria_form.html', {'form': form, 'titulo': 'Editar categoria'})


@proprietario_required
def categoria_delete(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        try:
            categoria.delete()
            messages.success(request, 'Categoria excluída.')
        except ProtectedError:
            messages.error(request, 'Esta categoria tem produtos vinculados e não pode ser excluída.')
        return redirect('categoria_list')
    return render(request, 'estoque/categoria_confirm_delete.html', {'categoria': categoria})


# ---------- Produtos ----------

@login_required
def produto_list(request):
    produtos = Produto.objects.select_related('categoria').order_by('nome')
    return render(request, 'estoque/produto_list.html', {
        'produtos': produtos,
        'pode_editar': eh_proprietario(request.user),
    })


@proprietario_required
def produto_create(request):
    form = ProdutoForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Produto cadastrado.')
        return redirect('produto_list')
    return render(request, 'estoque/produto_form.html', {'form': form, 'titulo': 'Novo produto'})


@proprietario_required
def produto_update(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    form = ProdutoForm(request.POST or None, instance=produto)
    if form.is_valid():
        form.save()
        messages.success(request, 'Produto atualizado.')
        return redirect('produto_list')
    return render(request, 'estoque/produto_form.html', {'form': form, 'titulo': 'Editar produto'})


@proprietario_required
def produto_delete(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    if request.method == 'POST':
        try:
            produto.delete()
            messages.success(request, 'Produto excluído.')
        except ProtectedError:
            messages.error(request, 'Este produto tem movimentações registradas e não pode ser excluído.')
        return redirect('produto_list')
    return render(request, 'estoque/produto_confirm_delete.html', {'produto': produto})


# ---------- Movimentações ----------

@login_required
def movimentacao_list(request):
    movs = Movimentacao.objects.select_related('produto', 'usuario').order_by('-data', '-id')

    filtro = FiltroMovimentacaoForm(request.GET or None)
    if filtro.is_valid():
        dados = filtro.cleaned_data
        if dados['produto']:
            movs = movs.filter(produto=dados['produto'])
        if dados['tipo']:
            movs = movs.filter(tipo=dados['tipo'])
        if dados['usuario']:
            movs = movs.filter(usuario=dados['usuario'])
        if dados['data_inicio']:
            movs = movs.filter(data__date__gte=dados['data_inicio'])
        if dados['data_fim']:
            movs = movs.filter(data__date__lte=dados['data_fim'])

    paginator = Paginator(movs, 25)
    page = paginator.get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'estoque/movimentacao_list.html', {
        'page': page,
        'filtro': filtro,
        'total': paginator.count,
        'querystring': params.urlencode(),
    })


@login_required
def movimentacao_create(request):
    form = MovimentacaoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            produto = Produto.objects.select_for_update().get(pk=form.cleaned_data['produto'].pk)
            mov = form.save(commit=False)

            if mov.tipo == Movimentacao.SAIDA and mov.quantidade > produto.quantidade:
                form.add_error(None, f'Estoque insuficiente: há apenas {produto.quantidade} unidade(s).')
            else:
                mov.usuario = request.user
                if mov.tipo == Movimentacao.ENTRADA:
                    produto.quantidade += mov.quantidade
                else:
                    produto.quantidade -= mov.quantidade
                produto.save(update_fields=['quantidade'])
                mov.save()

                messages.success(request, 'Movimentação registrada.')
                if produto.abaixo_do_minimo:
                    messages.warning(
                        request,
                        f'Atenção: "{produto.nome}" está abaixo do estoque mínimo '
                        f'({produto.quantidade} de {produto.estoque_minimo}).'
                    )
                return redirect('movimentacao_list')
    return render(request, 'estoque/movimentacao_form.html', {'form': form})


# ---------- Usuários ----------

@proprietario_required
def usuario_list(request):
    usuarios = list(
        User.objects.annotate(total_mov=Count('movimentacoes'))
        .prefetch_related('groups')
        .order_by('first_name', 'username')
    )
    for u in usuarios:
        u.perfil = perfil_do_usuario(u)
    return render(request, 'estoque/usuario_list.html', {'usuarios': usuarios})


@proprietario_required
def usuario_create(request):
    form = UsuarioCreateForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Usuário criado.')
        return redirect('usuario_list')
    return render(request, 'estoque/usuario_form.html', {
        'form': form, 'titulo': 'Novo usuário', 'ajuda': AJUDA_SENHA,
    })


@proprietario_required
def usuario_update(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    si_mesmo = usuario.pk == request.user.pk
    form = UsuarioEditForm(request.POST or None, usuario=usuario, editando_a_si_mesmo=si_mesmo)
    if form.is_valid():
        form.save()
        messages.success(request, 'Usuário atualizado.')
        return redirect('usuario_list')
    return render(request, 'estoque/usuario_form.html', {
        'form': form, 'titulo': f'Editar usuário: {usuario.username}',
    })


@proprietario_required
def usuario_password(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    form = NovaSenhaForm(request.POST or None, usuario=usuario)
    if form.is_valid():
        form.save()
        messages.success(request, f'Senha de "{usuario.username}" alterada.')
        return redirect('usuario_list')
    return render(request, 'estoque/usuario_form.html', {
        'form': form, 'titulo': f'Nova senha: {usuario.username}', 'ajuda': AJUDA_SENHA,
    })