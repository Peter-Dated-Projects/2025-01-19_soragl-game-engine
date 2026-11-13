#version 330 core

// one program for both meshes (in_position) and sprite quads (in_corner)
in vec3 in_position;

uniform mat4 m_light;
uniform mat4 m_model;
uniform bool u_sprite;
uniform vec3 u_anchor;
uniform vec3 u_right;
uniform vec3 u_up;
uniform vec4 u_uv_rect;

out vec2 v_uv;

void main() {
    vec3 world;
    if (u_sprite) {
        world = u_anchor + u_right * in_position.x + u_up * in_position.y;
        v_uv = vec2(mix(u_uv_rect.x, u_uv_rect.z, in_position.x + 0.5),
                    mix(u_uv_rect.w, u_uv_rect.y, in_position.y));
    } else {
        world = (m_model * vec4(in_position, 1.0)).xyz;
        v_uv = vec2(0.0);
    }
    gl_Position = m_light * vec4(world, 1.0);
}
