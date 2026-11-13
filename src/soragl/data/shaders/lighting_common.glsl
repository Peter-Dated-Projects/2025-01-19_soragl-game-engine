// Shared by the lit 3D shaders: one directional key light, ambient fill,
// a PCF shadow map and optional toon banding.
uniform sampler2D u_shadow_map;
uniform vec3 u_light_dir;   // the direction light travels, normalized
uniform vec3 u_light_color;
uniform vec3 u_ambient;
uniform int u_toon_bands;   // 0 = smooth lighting

float shadow_lit(vec4 light_pos, float bias) {
    vec3 p = light_pos.xyz / light_pos.w * 0.5 + 0.5;
    if (p.z > 1.0 || p.x < 0.0 || p.y < 0.0 || p.x > 1.0 || p.y > 1.0) return 1.0;
    vec2 texel = 1.0 / vec2(textureSize(u_shadow_map, 0));
    float lit = 0.0;
    for (int x = -1; x <= 1; x++)
        for (int y = -1; y <= 1; y++)
            lit += (p.z - bias > texture(u_shadow_map, p.xy + vec2(x, y) * texel).r) ? 0.0 : 1.0;
    return lit / 9.0;
}

vec3 shade(vec3 albedo, float n_dot_l, float lit) {
    float light = max(n_dot_l, 0.0) * lit;
    if (u_toon_bands > 0) light = floor(light * float(u_toon_bands) + 0.5) / float(u_toon_bands);
    return albedo * (u_ambient + u_light_color * light);
}
