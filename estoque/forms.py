from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Categoria, Movimentacao, Produto
from .perfis import PERFIS, PROPRIETARIO, VENDEDOR, perfil_do_usuario

User = get_user_model()


# ---------- Categoria ----------

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nome']

    def clean_nome(self):
        nome = self.cleaned_data['nome'].strip()
        existentes = Categoria.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError('Já existe uma categoria com esse nome.')
        return nome


# ---------- Produto ----------

class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ['nome', 'descricao', 'categoria', 'quantidade', 'valor', 'estoque_minimo']


# ---------- Movimentação ----------

class MovimentacaoForm(forms.ModelForm):
    class Meta:
        model = Movimentacao
        fields = ['produto', 'tipo', 'quantidade', 'valor_unitario']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['valor_unitario'].required = False
        self.fields['valor_unitario'].help_text = 'Deixe em branco para usar o valor atual do produto.'

    def clean(self):
        cleaned = super().clean()
        produto = cleaned.get('produto')
        tipo = cleaned.get('tipo')
        quantidade = cleaned.get('quantidade')

        if produto and not cleaned.get('valor_unitario'):
            cleaned['valor_unitario'] = produto.valor

        if produto and tipo == Movimentacao.SAIDA and quantidade and quantidade > produto.quantidade:
            raise forms.ValidationError(
                f'Estoque insuficiente: há apenas {produto.quantidade} unidade(s) de "{produto.nome}".'
            )
        return cleaned


class FiltroMovimentacaoForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.order_by('nome'), required=False, empty_label='Todos')
    tipo = forms.ChoiceField(
        choices=[('', 'Todos')] + Movimentacao.TIPO_CHOICES, required=False)
    usuario = forms.ModelChoiceField(
        queryset=User.objects.order_by('username'), required=False, empty_label='Todos')
    data_inicio = forms.DateField(
        required=False, label='De', widget=forms.DateInput(attrs={'type': 'date'}))
    data_fim = forms.DateField(
        required=False, label='Até', widget=forms.DateInput(attrs={'type': 'date'}))


# ---------- Usuários ----------

def _validar_senha(form, usuario):
    """Confere se as duas senhas batem e se a senha é aceitável. Os erros aparecem no formulário."""
    cleaned = form.cleaned_data
    p1, p2 = cleaned.get('password1'), cleaned.get('password2')
    if p1 and p2:
        if p1 != p2:
            form.add_error('password2', 'As senhas não são iguais.')
        else:
            try:
                validate_password(p1, user=usuario)
            except ValidationError as erro:
                form.add_error('password1', erro)


class UsuarioCreateForm(forms.Form):
    first_name = forms.CharField(label='Nome', max_length=150)
    username = forms.CharField(label='Usuário (usado para entrar)', max_length=150)
    perfil = forms.ChoiceField(label='Perfil', choices=PERFIS)
    password1 = forms.CharField(label='Senha', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Repita a senha', widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Já existe um usuário com esse nome de login.')
        return username

    def clean(self):
        cleaned = super().clean()
        temporario = User(
            username=cleaned.get('username', ''),
            first_name=cleaned.get('first_name', ''),
        )
        _validar_senha(self, temporario)
        return cleaned

    def save(self):
        cd = self.cleaned_data
        usuario = User.objects.create_user(
            username=cd['username'],
            password=cd['password1'],
            first_name=cd['first_name'],
        )
        grupo, _ = Group.objects.get_or_create(name=cd['perfil'])
        usuario.groups.set([grupo])
        return usuario


class UsuarioEditForm(forms.Form):
    first_name = forms.CharField(label='Nome', max_length=150)
    perfil = forms.ChoiceField(label='Perfil', choices=PERFIS)
    ativo = forms.BooleanField(label='Usuário ativo (pode entrar no sistema)', required=False)

    def __init__(self, *args, usuario, editando_a_si_mesmo=False, **kwargs):
        perfil_atual = perfil_do_usuario(usuario)
        kwargs.setdefault('initial', {
            'first_name': usuario.first_name,
            'perfil': perfil_atual if perfil_atual in (PROPRIETARIO, VENDEDOR) else VENDEDOR,
            'ativo': usuario.is_active,
        })
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if editando_a_si_mesmo:
            self.fields['perfil'].disabled = True
            self.fields['ativo'].disabled = True
            self.fields['perfil'].help_text = 'Você não pode mudar o próprio perfil nem se desativar.'

    def save(self):
        cd = self.cleaned_data
        self.usuario.first_name = cd['first_name']
        self.usuario.is_active = cd['ativo']
        self.usuario.save()
        grupo, _ = Group.objects.get_or_create(name=cd['perfil'])
        self.usuario.groups.set([grupo])
        return self.usuario


class NovaSenhaForm(forms.Form):
    password1 = forms.CharField(label='Nova senha', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Repita a nova senha', widget=forms.PasswordInput)

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean(self):
        cleaned = super().clean()
        _validar_senha(self, self.usuario)
        return cleaned

    def save(self):
        self.usuario.set_password(self.cleaned_data['password1'])
        self.usuario.save()
        return self.usuario