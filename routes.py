from flask import jsonify, render_template, redirect, url_for, flash, request, session, Response
from urllib.parse import urlparse
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import desc
from datetime import datetime
import json
import os
import uuid

from app import app, db
from models import User, Conversation, Message, PremiumSubscription
from forms import LoginForm, RegistrationForm, ChatForm, UserAdminForm
from gemini_connector import generate_response, generate_with_history
from utils import get_model_settings

# Página principal - Aplicación de página única
@app.route('/')
def index():
    return render_template('single_page.html')

# ===== Rutas de autenticación tradicionales =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Usuario o contraseña inválidos')
            return redirect(url_for('login'))
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('index')
        
        return redirect(next_page)
    
    return render_template('login.html', title='Iniciar Sesión', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash('¡Te has registrado exitosamente!')
        return redirect(url_for('login'))
    
    return render_template('register.html', title='Registro', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# ===== API Endpoints para SPA =====
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    remember = data.get('remember', False)
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Se requiere nombre de usuario y contraseña'}), 400
    
    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({'success': False, 'message': 'Usuario o contraseña inválidos'}), 401
    
    login_user(user, remember=remember)
    
    return jsonify({
        'success': True,
        'message': '¡Has iniciado sesión exitosamente!',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_premium': user.is_premium,
            'is_admin': user.is_admin
        }
    })

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    password2 = data.get('password2')
    
    if not username or not email or not password or not password2:
        return jsonify({'success': False, 'message': 'Todos los campos son requeridos'}), 400
    
    if password != password2:
        return jsonify({'success': False, 'message': 'Las contraseñas no coinciden'}), 400
    
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'La contraseña debe tener al menos 8 caracteres'}), 400
    
    # Verificar si el usuario ya existe
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'El nombre de usuario ya está en uso'}), 400
    
    # Verificar si el email ya existe
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'El email ya está registrado'}), 400
    
    # Crear nuevo usuario
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    # Iniciar sesión automáticamente
    login_user(user)
    
    return jsonify({
        'success': True,
        'message': '¡Te has registrado exitosamente!',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_premium': user.is_premium,
            'is_admin': user.is_admin
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    logout_user()
    return jsonify({'success': True, 'message': 'Has cerrado sesión correctamente'})

@app.route('/api/auth/user', methods=['GET'])
def api_user():
    if current_user.is_authenticated:
        return jsonify({
            'success': True,
            'authenticated': True,
            'user': {
                'id': current_user.id,
                'username': current_user.username,
                'email': current_user.email,
                'is_premium': current_user.is_premium,
                'is_admin': current_user.is_admin
            }
        })
    else:
        return jsonify({
            'success': True,
            'authenticated': False
        })

# ===== API Endpoints para Conversaciones =====
@app.route('/api/conversations', methods=['GET'])
@login_required
def api_get_conversations():
    conversations = Conversation.query.filter_by(user_id=current_user.id).order_by(desc(Conversation.updated_at)).all()
    return jsonify({
        'success': True,
        'conversations': [{
            'id': conv.id,
            'title': conv.title,
            'created_at': conv.created_at.isoformat(),
            'updated_at': conv.updated_at.isoformat()
        } for conv in conversations]
    })

@app.route('/api/conversations', methods=['POST'])
@login_required
def api_create_conversation():
    data = request.json
    title = data.get('title', 'Nueva Conversación')
    
    conversation = Conversation(title=title, user_id=current_user.id)
    db.session.add(conversation)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'conversation': {
            'id': conversation.id,
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat(),
            'updated_at': conversation.updated_at.isoformat()
        }
    })

@app.route('/api/conversations/<int:conversation_id>', methods=['GET'])
@login_required
def api_get_conversation(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
    messages = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.timestamp).all()
    
    return jsonify({
        'success': True,
        'conversation': {
            'id': conversation.id,
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat(),
            'updated_at': conversation.updated_at.isoformat(),
            'messages': [{
                'id': msg.id,
                'content': msg.content,
                'is_user': msg.is_user,
                'timestamp': msg.timestamp.isoformat()
            } for msg in messages]
        }
    })

@app.route('/api/conversations/<int:conversation_id>', methods=['PUT'])
@login_required
def api_update_conversation(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
    data = request.json
    
    if 'title' in data:
        conversation.title = data['title']
        conversation.updated_at = datetime.utcnow()
        db.session.commit()
    
    return jsonify({
        'success': True,
        'conversation': {
            'id': conversation.id,
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat(),
            'updated_at': conversation.updated_at.isoformat()
        }
    })

@app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
@login_required
def api_delete_conversation(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
    db.session.delete(conversation)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Conversación eliminada'
    })

# ===== API Endpoints para Mensajes =====
@app.route('/api/conversations/<int:conversation_id>/messages', methods=['POST'])
@login_required
def api_send_message(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
    data = request.json
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'success': False, 'message': 'El mensaje no puede estar vacío'}), 400
    
    # Guardar mensaje del usuario
    user_msg = Message(content=user_message, is_user=True, conversation_id=conversation.id)
    db.session.add(user_msg)
    
    # Actualizar timestamp de la conversación
    conversation.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': {
            'id': user_msg.id,
            'content': user_msg.content,
            'is_user': user_msg.is_user,
            'timestamp': user_msg.timestamp.isoformat()
        }
    })

@app.route('/api/conversations/<int:conversation_id>/messages/stream', methods=['POST'])
@login_required
def api_stream_response(conversation_id):
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first_or_404()
    data = request.json
    
    # Obtener todos los mensajes de la conversación para el historial
    messages = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.timestamp).all()
    message_history = [
        {
            'content': msg.content,
            'is_user': msg.is_user
        } for msg in messages
    ]
    
    # Obtener configuración del modelo según el nivel del usuario
    model_settings = get_model_settings(current_user.is_premium)
    
    def generate():
        try:
            ai_response = ""
            
            # Generar respuesta con historial
            for chunk in generate_with_history(message_history):
                if hasattr(chunk, 'text'):
                    piece = chunk.text
                    ai_response += piece
                    yield f"data: {json.dumps({'chunk': piece, 'done': False})}\n\n"
            
            # Guardar respuesta completa en la base de datos
            ai_msg = Message(content=ai_response, is_user=False, conversation_id=conversation.id)
            db.session.add(ai_msg)
            db.session.commit()
            
            yield f"data: {json.dumps({'chunk': '', 'done': True, 'messageId': ai_msg.id})}\n\n"
            
        except Exception as e:
            app.logger.error(f"Error al generar respuesta: {str(e)}")
            error_message = f"Lo siento, ocurrió un error al generar la respuesta: {str(e)}"
            yield f"data: {json.dumps({'error': error_message})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

# ===== API Endpoints para Suscripciones Premium =====
@app.route('/api/premium/create-subscription', methods=['POST'])
@login_required
def api_create_premium_subscription():
    # Verificar si el usuario ya es premium
    if current_user.is_premium:
        return jsonify({
            'success': False,
            'message': 'Ya eres un usuario premium'
        }), 400
    
    # Generar referencia única para la transacción
    reference_id = f"PREMIUM-{uuid.uuid4().hex[:8].upper()}"
    
    # Precio de la suscripción premium
    amount = 2500.00  # $2500 ARS
    
    # Crear suscripción pendiente
    subscription = PremiumSubscription(
        reference_id=reference_id,
        amount=amount,
        status='pending',
        payment_method='bank_transfer',
        user_id=current_user.id
    )
    
    db.session.add(subscription)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'subscription': {
            'reference_id': subscription.reference_id,
            'amount': subscription.amount,
            'status': subscription.status,
            'created_at': subscription.created_at.isoformat()
        },
        'payment_details': {
            'cbu': '0000003100005229414401',
            'amount': amount,
            'reference': reference_id
        }
    })

@app.route('/api/premium/check-status', methods=['GET'])
@login_required
def api_check_premium_status():
    subscription = PremiumSubscription.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(PremiumSubscription.created_at)).first()
    
    if not subscription:
        return jsonify({
            'success': True,
            'has_subscription': False
        })
    
    return jsonify({
        'success': True,
        'has_subscription': True,
        'subscription': {
            'reference_id': subscription.reference_id,
            'amount': subscription.amount,
            'status': subscription.status,
            'created_at': subscription.created_at.isoformat(),
            'updated_at': subscription.updated_at.isoformat()
        },
        'payment_details': {
            'cbu': '0000003100005229414401',
            'amount': subscription.amount,
            'reference': subscription.reference_id
        }
    })

# ===== API Endpoints para Administración =====
@app.route('/api/admin/users', methods=['GET'])
@login_required
def api_get_users():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acceso denegado'}), 403
    
    users = User.query.all()
    return jsonify({
        'success': True,
        'users': [{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_premium': user.is_premium,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat()
        } for user in users]
    })

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
def api_update_user(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acceso denegado'}), 403
    
    user = User.query.get_or_404(user_id)
    data = request.json
    
    if 'is_premium' in data:
        user.is_premium = bool(data['is_premium'])
    
    if 'is_admin' in data:
        # No permitir que un administrador se quite a sí mismo los permisos
        if user.id == current_user.id and not bool(data['is_admin']):
            return jsonify({'success': False, 'message': 'No puedes quitarte a ti mismo los permisos de administrador'}), 400
        user.is_admin = bool(data['is_admin'])
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_premium': user.is_premium,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat()
        }
    })
    
@app.route('/api/admin/subscriptions', methods=['GET'])
@login_required
def api_get_subscriptions():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acceso denegado'}), 403
    
    subscriptions = PremiumSubscription.query.order_by(desc(PremiumSubscription.created_at)).all()
    return jsonify({
        'success': True,
        'subscriptions': [{
            'id': sub.id,
            'reference_id': sub.reference_id,
            'amount': sub.amount,
            'status': sub.status,
            'payment_method': sub.payment_method,
            'created_at': sub.created_at.isoformat(),
            'updated_at': sub.updated_at.isoformat(),
            'user_id': sub.user_id,
            'username': User.query.get(sub.user_id).username
        } for sub in subscriptions]
    })
    
@app.route('/api/admin/subscriptions/<int:subscription_id>/approve', methods=['POST'])
@login_required
def api_approve_subscription(subscription_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Acceso denegado'}), 403
    
    subscription = PremiumSubscription.query.get_or_404(subscription_id)
    
    if subscription.status == 'completed':
        return jsonify({'success': False, 'message': 'Esta suscripción ya ha sido aprobada'}), 400
    
    # Actualizar estado de la suscripción
    subscription.status = 'completed'
    subscription.updated_at = datetime.utcnow()
    
    # Actualizar usuario a premium
    user = User.query.get(subscription.user_id)
    user.is_premium = True
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Suscripción aprobada correctamente',
        'subscription': {
            'id': subscription.id,
            'reference_id': subscription.reference_id,
            'status': subscription.status,
            'updated_at': subscription.updated_at.isoformat()
        },
        'user': {
            'id': user.id,
            'username': user.username,
            'is_premium': user.is_premium
        }
    })