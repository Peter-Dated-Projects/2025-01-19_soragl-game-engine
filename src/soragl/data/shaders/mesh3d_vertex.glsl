#version 330 core

in vec3 in_position;
in vec2 in_uv;
in vec3 in_normal;

uniform mat4 m_proj;
uniform mat4 m_view;
uniform mat4 m_model;
uniform mat4 m_light;

out vec3 v_normal;
out vec2 v_uv;
out vec4 v_light_pos;

void main() {
    vec4 world = m_model * vec4(in_position, 1.0);
    v_normal = mat3(transpose(inverse(m_model))) * in_normal;
    v_uv = in_uv;
    v_light_pos = m_light * world;
    gl_Position = m_proj * m_view * world;
}
