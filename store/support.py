"""Store panel: return requests and customer questions."""
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.services import notify
from orders.models import ReturnRequest
from products.models import Question

from .access import store_view
from .forms import AnswerForm, ReturnDecisionForm
from .views import paginate, redirect_back, render_store


@store_view('orders.change_returnrequest')
def return_list(request):
    tab = request.GET.get('status', 'pending')
    returns = ReturnRequest.objects.select_related('order')
    if tab in ReturnRequest.Status.values:
        returns = returns.filter(status=tab)
    tabs = [(value, label) for value, label in ReturnRequest.Status.choices] + [('all', 'All')]
    return render_store(request, 'store/returns.html', {
        'page_obj': paginate(request, returns), 'tab': tab, 'tabs': tabs, 'decision_form': ReturnDecisionForm(),
    }, section='store:returns')


@require_POST
@store_view('orders.change_returnrequest')
def return_decide(request, pk):
    rr = get_object_or_404(ReturnRequest, pk=pk)
    form = ReturnDecisionForm(request.POST)
    if form.is_valid():
        rr.status = form.cleaned_data['status']
        rr.admin_note = form.cleaned_data['admin_note'] or rr.admin_note
        rr.save()  # the signal notifies the customer
        messages.success(request, f'Return for {rr.order.order_number} marked {rr.get_status_display()}.')
    else:
        messages.error(request, 'Choose a decision.')
    return redirect_back(request, 'store:returns')


@store_view('products.change_question')
def question_list(request):
    tab = request.GET.get('show', 'unanswered')
    questions = Question.objects.select_related('product', 'user', 'answered_by')
    if tab == 'unanswered':
        questions = questions.filter(answered_at__isnull=True)
    elif tab == 'answered':
        questions = questions.filter(answered_at__isnull=False)
    return render_store(request, 'store/questions.html', {'page_obj': paginate(request, questions), 'tab': tab},
                        section='store:questions')


@require_POST
@store_view('products.change_question')
def question_answer(request, pk):
    question = get_object_or_404(Question.objects.select_related('product', 'user'), pk=pk)
    if 'toggle_publish' in request.POST:
        question.is_published = not question.is_published
        question.save(update_fields=['is_published'])
        messages.success(request, 'Question is now ' + ('shown on the product page.' if question.is_published
                                                       else 'hidden.'))
        return redirect_back(request, 'store:questions')
    form = AnswerForm(request.POST)
    if form.is_valid():
        first_answer = not question.answered_at
        question.answer = form.cleaned_data['answer']
        question.answered_by = request.user
        question.answered_at = timezone.now()
        question.save(update_fields=['answer', 'answered_by', 'answered_at'])
        if first_answer:
            notify(question.user, f'Your question about "{question.product.title}" has been answered.',
                   url=question.product.get_absolute_url() + '#questions', icon='chat-left-dots')
        messages.success(request, 'Answer posted on the product page.')
    else:
        messages.error(request, 'Write an answer first.')
    return redirect_back(request, 'store:questions')
