#version 330 core
#include lighting_common

uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_alpha_cutoff;
uniform bool u_unlit;

in vec2 v_uv;
flat in vec4 v_anchor_light_pos;

out vec4 f_color;

void main() {
    vec4 albedo = texture(u_texture, v_uv) * u_color;
    if (albedo.a < u_alpha_cutoff) discard;
    if (u_unlit) { f_color = vec4(albedo.rgb, 1.0); return; }
    f_color = vec4(shade(albedo.rgb, 1.0, shadow_lit(v_anchor_light_pos, 0.003)), 1.0);
}
