from django.urls import path
from . import views

app_name = 'accounts'
urlpatterns = [
    path('login/',                 views.LoginView.as_view(),    name='login'),
    path('logout/',                views.LogoutView.as_view(),   name='logout'),
    path('users/',                 views.UserListView.as_view(), name='user_list'),
    path('users/create/',          views.CreateUserView.as_view(),name='create_user'),
    path('users/<int:pk>/edit/',   views.EditUserView.as_view(), name='edit_user'),
    path('users/<int:pk>/delete/', views.delete_user,            name='delete_user'),
]
