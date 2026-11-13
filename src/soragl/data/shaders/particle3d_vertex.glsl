#version 330 core

in vec2 in_corner;      // unit quad, x and y in [-0.5, 0.5]
in vec3 in_center;      // per instance
in float in_size;
in vec4 in_color;

uniform mat4 m_proj;
uniform mat4 m_view;
uniform vec3 u_cam_right;
uniform vec3 u_cam_up;

out vec2 v_corner;
out vec4 v_color;

void main() {
    v_corner = in_corner;
    v_color = in_color;
    vec3 world = in_center + (u_cam_right * in_corner.x + u_cam_up * in_corner.y) * in_size;
    gl_Position = m_proj * m_view * vec4(world, 1.0);
}
