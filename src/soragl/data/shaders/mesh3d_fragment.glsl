#version 330 core
#include lighting_common

uniform sampler2D u_texture;
uniform vec4 u_color;
uniform bool u_unlit;

in vec3 v_normal;
in vec2 v_uv;
in vec4 v_light_pos;

out vec4 f_color;

void main() {
    vec4 albedo = texture(u_texture, v_uv) * u_color;
    if (albedo.a < 0.5) discard;
    if (u_unlit) { f_color = albedo; return; }
    float n_dot_l = dot(normalize(v_normal), -u_light_dir);
    float bias = max(0.004 * (1.0 - n_dot_l), 0.001);
    f_color = vec4(shade(albedo.rgb, n_dot_l, shadow_lit(v_light_pos, bias)), albedo.a);
}
