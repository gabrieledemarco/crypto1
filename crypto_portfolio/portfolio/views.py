# Create your views here.
# views.py


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from .forms import RegistrationForm
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render
from django.http import HttpResponse

from .UpdateClientTable import UpdateClientTable
from .DbService import DbService

@login_required
def home(request):
    # print("Richiesta è:", request)
    if request.user.is_authenticated:
        #   print("Richiesta è:", request)
        # Recupera l'API key cifrata dal database
        api_key = request.user.api_key
        username = request.user.username
        id_user = request.user.id
        auth_state = request.user.is_active
        return render(request, 'home.html', {'username': username, 'id_user': id_user,
                                             'auth_state': auth_state, 'api_key': api_key})
    else:
        return redirect('login')  # Reindirizza alla pagina di login se non autenticato


def aggiorna_dati(request):
    # Simulazione dell'aggiornamento dati (sostituisci con la tua logica)
    print("Aggiornamento dati avviato...")
    UpdateClientTable(user_id=request.user.id).update_all_table()
    return HttpResponse("Aggiornamento completato!")


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # Ottieni l'oggetto user dal form
            user = form.save(commit=False)

            user.set_password(form.cleaned_data['password1'])
            user.save()  # Ora salva l'utente nel database

            # Autenticazione e login dell'utente
            user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])

            login(request, user)
            return redirect('home')
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        print("form valid", form.is_valid())
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Salva informazioni aggiuntive nella sessione

            request.session['user_email'] = user.email  # Puoi salvare altre informazioni se necessario
            print("user è:", form.get_user())
            print("email è:", user.email)
            return redirect('home')
        else:

            print(form.errors)  # Stampa gli errori per il debug
    else:
        form = AuthenticationForm()
        print(form.errors)
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)

    # Rimuovi le informazioni dalla sessione se necessario

    request.session.pop('user_email', None)  # Rimuovi l'email dalla sessione

    return redirect('login')  # Reindirizza alla pagina di login
