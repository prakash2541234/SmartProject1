from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.views import View

from .models import User, PatientProfile, ClinicianProfile
from .forms  import LoginForm, CreateUserForm, EditUserForm
from .decorators import role_required


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:home')
        return render(request, 'accounts/login.html', {'form': LoginForm()})

    def post(self, request):
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'])
            if user and user.is_active:
                login(request, user)
                return redirect('dashboard:home')
            messages.error(request, 'Invalid username or password.')
        return render(request, 'accounts/login.html', {'form': form})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('accounts:login')


@method_decorator([login_required, role_required('admin')], name='dispatch')
class UserListView(View):
    def get(self, request):
        return render(request, 'accounts/user_list.html', {
            'users': User.objects.all().order_by('role','last_name'),
        })


@method_decorator([login_required, role_required('admin')], name='dispatch')
class CreateUserView(View):
    def get(self, request):
        return render(request, 'accounts/create_user.html', {
            'form': CreateUserForm(),
            'clinicians': User.objects.filter(role='clinician'),
        })

    def post(self, request):
        form = CreateUserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            role = form.cleaned_data['role']
            if role == 'patient':
                cid = request.POST.get('clinician_id')
                clinician = User.objects.filter(pk=cid, role='clinician').first()
                PatientProfile.objects.create(user=user, clinician=clinician)
            elif role == 'clinician':
                ClinicianProfile.objects.create(
                    user=user,
                    department=request.POST.get('department',''),
                    license_number=request.POST.get('license_number',''),
                )
            messages.success(request, f'User "{user.username}" created.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/create_user.html', {
            'form': form,
            'clinicians': User.objects.filter(role='clinician'),
        })


@method_decorator([login_required, role_required('admin')], name='dispatch')
class EditUserView(View):
    def get(self, request, pk):
        u = get_object_or_404(User, pk=pk)
        return render(request, 'accounts/edit_user.html', {
            'edit_user': u,
            'form': EditUserForm(instance=u),
            'clinicians': User.objects.filter(role='clinician'),
            'pp': getattr(u, 'patient_profile', None),
        })

    def post(self, request, pk):
        u = get_object_or_404(User, pk=pk)
        form = EditUserForm(request.POST, instance=u)
        if form.is_valid():
            user = form.save(commit=False)
            pw = form.cleaned_data.get('new_password','').strip()
            if pw: user.set_password(pw)
            user.save()
            if u.role == 'patient':
                cid = request.POST.get('clinician_id')
                clinician = User.objects.filter(pk=cid, role='clinician').first()
                pp, _ = PatientProfile.objects.get_or_create(user=u)
                pp.clinician = clinician; pp.save()
            messages.success(request, 'User updated.')
            return redirect('accounts:user_list')
        return render(request, 'accounts/edit_user.html', {
            'edit_user': u, 'form': form,
            'clinicians': User.objects.filter(role='clinician'),
        })


@login_required
@role_required('admin')
def delete_user(request, pk):
    if request.method == 'POST':
        u = get_object_or_404(User, pk=pk)
        if u.pk == request.user.pk:
            messages.error(request, "Cannot delete your own account.")
        else:
            u.delete()
            messages.success(request, 'User deleted.')
    return redirect('accounts:user_list')
