# Documentación Técnica - FNOGUERA CLUSTER

Este documento explica las decisiones arquitectónicas y tecnológicas tomadas para el desarrollo del portal FNOGUERA CLUSTER.

## 1. ¿Por qué usar un portal en vez de Google Forms?

Aunque herramientas como Google Forms son útiles para la recolección básica de datos, un portal dedicado ofrece ventajas fundamentales para un entorno de computación de alto rendimiento:

* **Integración y Trazabilidad:** El portal está vinculado directamente a la base de datos central (`CLUSTER_NIDTEC`). Esto permite que cada solicitud tenga un historial completo y un estado (Pendiente, Aceptada, Rechazada) que el usuario puede consultar en tiempo real.
* **Gestión de Ciclo de Vida:** Un portal permite procesos complejos. Por ejemplo, al aceptar una solicitud, el administrador puede asignar recursos específicos (vCPUs, RAM, GPUs) que quedan registrados para esa sesión de investigación.
* **Seguridad e Identidad:** El sistema maneja cuentas de usuario con roles (Administrador vs. Investigador). Esto garantiza que solo personas autorizadas puedan solicitar recursos o gestionar el sistema, manteniendo un registro de auditoría de quién autorizó qué.
* **Potencial de Automatización:** El portal es el primer eslabón hacia la automatización total. Está diseñado para integrarse en el futuro con orquestadores como **Slurm**, permitiendo que la aprobación de una solicitud cree automáticamente los accesos en los nodos del Cluster.

## 2. ¿Qué Ingeniería de Software se utiliza en este proyecto?

El desarrollo se fundamenta en estándares de ingeniería modernos para asegurar robustez, seguridad y escalabilidad:

* **Arquitectura Multinivel (N-Layer):** El sistema separa estrictamente la capa de presentación (Frontend), la lógica de negocio (Backend) y la persistencia de datos (Base de Datos).
* **Patrón de Diseño MVC (Modelo-Vista-Controlador):**
  * **Modelos:** Implementados con **SQLAlchemy** (ORM), permitiendo una gestión de datos orientada a objetos.
  * **Vistas:** Creadas con el motor de plantillas **Jinja2**, HTML5 y CSS3, asegurando una interfaz dinámica y responsiva.
  * **Controlador:** Rutas de **Flask** que procesan las peticiones del usuario, validan datos y coordinan la respuesta del servidor.
* **Seguridad por Diseño (Security by Design):**
  * Uso de **Bcrypt** para el hashing unidireccional de contraseñas.
  * Protección contra ataques comunes (CSRF, Inyección SQL a través del ORM).
  * Manejo de sesiones cifradas para la autenticación.
* **Principios de UI/UX:** Implementación de estéticas profesionales (*Glassmorphism*) y jerarquía visual clara para mejorar la experiencia del investigador y reducir errores en la carga de datos.
* **Metodología de Desarrollo:** Enfoque iterativo e incremental, permitiendo la validación de funcionalidades clave (como el sistema de solicitudes) antes de avanzar hacia integraciones más complejas.
