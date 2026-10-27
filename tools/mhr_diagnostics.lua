-- Temporary read-only probe; writes diagnostics without changing game data.
local last = -10
local names = {player="snow.player.PlayerManager",quest="snow.QuestManager",game="snow.SnowGameManager",enemy="snow.enemy.EnemyManager",message="snow.gui.MessageManager"}
re.on_frame(function()
    if os.clock() - last < 5 then return end
    last = os.clock()
    local result = {time=last, managers={}, has_d2d=d2d~=nil}
    for key,name in pairs(names) do
        local ok,value=pcall(sdk.get_managed_singleton,name)
        result.managers[key] = ok and value~=nil
    end
    if d2d and d2d.detail and d2d.detail.get_last_error then
        local ok,message=pcall(d2d.detail.get_last_error)
        result.d2d_error=ok and message or tostring(message)
    end
    local ok,errors=pcall(require,"MHR_Overlay.Misc.error_handler")
    if ok then result.errors=errors.list end
    local ok2,flow=pcall(require,"MHR_Overlay.Game_Handler.quest_status")
    if ok2 then result.flow_state=flow.flow_state end
    local success,err=pcall(json.dump_file,"MHRMods/diagnostics.json",result)
    if not success then log.error("[MHRMods diagnostics] "..tostring(err)) end
end)
