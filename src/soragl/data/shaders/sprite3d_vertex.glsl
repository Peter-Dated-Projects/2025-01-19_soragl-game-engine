#version 330 core

// unit quad: x in [-0.5, 0.5], y in [0, 1], anchored at the sprite's feet
in vec3 in_corner;

uniform mat4 m_proj;
uniform mat4 m_view;
uniform mat4 m_light;
uniform vec3 u_anchor;
uniform vec3 u_right;   // world-space axes of the quad, already scaled by size
uniform vec3 u_up;
uniform vec4 u_uv_rect; // u0, v0 (top), u1, v1 (bottom)

out vec2 v_uv;
flat out vec4 v_anchor_light_pos;

void main() {
    vec3 world = u_anchor + u_right * in_corner.x + u_up * in_corner.y;
    v_uv = vec2(mix(u_uv_rect.x, u_uv_rect.z, in_corner.x + 0.5),
                mix(u_uv_rect.w, u_uv_rect.y, in_corner.y));
    // sprites take the shadow at their feet, so a flat sprite never shadows itself
    v_anchor_light_pos = m_light * vec4(u_anchor + vec3(0.0, 0.05, 0.0), 1.0);
    gl_Position = m_proj * m_view * vec4(world, 1.0);
}
