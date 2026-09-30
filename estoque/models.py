from django.db import models

# Create your models here.
class Categoria(models.Model):
    nome = models.CharField(max_length=100)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name_plural = 'categorias'

class Produto(models.Model):
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='produtos')
    quantidade = models.PositiveIntegerField(default=0)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    estoque_minimo = models.PositiveBigIntegerField(default=0 )

    def __str__(self):
        return self.nome

